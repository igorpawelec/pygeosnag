"""Band-mode resolution and feature-name layout."""
import pytest

from pygeosnag.features import feature_names
from pygeosnag.modes import MODES, guess_band_order, resolve_mode


def test_defaults():
    m, idx = resolve_mode(4)
    assert m.name == "rgbn" and idx == {"red": 0, "green": 1, "blue": 2, "nir": 3}
    m, idx = resolve_mode(3)
    assert m.name == "rgb" and idx == {"red": 0, "green": 1, "blue": 2}
    m, idx = resolve_mode(3, mode="cir")
    assert m.name == "cir" and idx == {"nir": 0, "red": 1, "green": 2}


def test_explicit_band_order():
    m, idx = resolve_mode(4, bands=("nir", "red", "green", "blue"))
    assert m.name == "rgbn" and idx == {"red": 1, "green": 2, "blue": 3, "nir": 0}
    m, idx = resolve_mode(5, mode="rgb", bands=("x", "red", "green", "blue", "nir"))
    assert idx == {"red": 1, "green": 2, "blue": 3}


def test_missing_role_is_an_error():
    with pytest.raises(ValueError):
        resolve_mode(3, mode="rgbn")
    with pytest.raises(ValueError):
        resolve_mode(4, bands=("red", "green", "blue", "swir"))
    with pytest.raises(ValueError):
        resolve_mode(4, mode="lidar")


def test_feature_layout_matches_the_research_names():
    assert feature_names(MODES["rgbn"]) == [
        "sr.NDVI", "sd.NDVI", "ktr.NDVI", "sr.NDGR", "sd.NDGR", "ktr.NDGR", "sr.NDBR", "sd.NDBR", "ktr.NDBR",
        "sr.L", "sd.L", "ktr.L", "sr.C", "sd.C", "ktr.C", "cos.Hab", "sin.Hab", "war.Hab", "pow.m2", "wydluzenie"]
    assert len(feature_names(MODES["cir"])) == 17 and "sr.NDBR" not in feature_names(MODES["cir"])
    assert len(feature_names(MODES["rgb"])) == 17 and "sr.NDVI" not in feature_names(MODES["rgb"])


def test_thresholds_are_the_matched_granularity():
    assert MODES["rgbn"].threshold == 60 and MODES["cir"].threshold == 50 and MODES["rgb"].threshold == 40


def test_guess_band_order_from_vegetation_medians():
    mode, bands, why = guess_band_order((124, 64, 85))          # a CIR orthophoto: red darkest
    assert mode == "cir" and bands == ("nir", "red", "green") and "darkest" in why
    mode, bands, _ = guess_band_order((70, 90, 60))             # RGB over canopy: green brightest
    assert mode == "rgb" and bands == ("red", "green", "blue")
    mode, bands, _ = guess_band_order((130, 60, 80, 50))        # NIR first
    assert mode == "rgbn" and bands == ("nir", "red", "green", "blue")
    mode, bands, _ = guess_band_order((60, 80, 50, 130))        # R, G, B, NIR
    assert mode == "rgbn" and bands == ("red", "green", "blue", "nir")
    assert guess_band_order((100, 80, 60))[0] is None           # bare ground: nothing certain
    assert guess_band_order((100, 98, 120))[0] is None          # margin too small
