"""Radiometry matching: what triggers it, what it does to the pixels."""
import numpy as np

from pygeosnag.radiometry import REFERENCE, Radiometry


def _scene(lo, hi, n=20000, seed=0):
    rng = np.random.default_rng(seed)
    return np.clip(rng.uniform(lo, hi, n), 0, 255)


def test_hazy_scene_triggers_and_maps_onto_the_reference():
    # red 56-123 like the Radom 2017 scene: dark end far above the reference 29
    rad = Radiometry("auto").fit({"red": _scene(56, 123), "nir": _scene(57, 119)})
    assert rad.active and any("dark end" in r for r in rad.reasons)
    a = np.linspace(56, 123, 100, dtype=np.float32).reshape(10, 10)
    out = rad.apply({"red": a})["red"]
    r_lo, r_hi = REFERENCE["red"]
    assert abs(out.min() - r_lo) < 3 and abs(out.max() - r_hi) < 3
    assert "matched" in rad.describe()


def test_scene_within_the_corridor_is_untouched():
    rad = Radiometry("auto").fit({"red": _scene(25, 85), "nir": _scene(45, 150)})
    assert not rad.active and rad.reasons == []
    a = np.full((5, 5), 70.0, np.float32)
    assert np.array_equal(rad.apply({"red": a})["red"], a)
    assert "untouched" in rad.describe()


def test_flat_scene_triggers_on_range_and_match_forces():
    rad = Radiometry("auto").fit({"nir": _scene(60, 110)})      # range 50 < 0.7 * 94
    assert rad.active and any("range" in r for r in rad.reasons)
    forced = Radiometry("match").fit({"red": _scene(25, 85)})
    assert forced.active and forced.reasons == []
    off = Radiometry("off")
    assert off.apply({"red": np.ones((2, 2))})["red"].sum() == 4


def test_unknown_role_and_too_few_pixels_pass_through():
    rad = Radiometry("match").fit({"red": _scene(56, 123), "swir": _scene(1, 2), "blue": np.zeros(10)})
    assert "blue" not in rad.scene                      # too few pixels: not measured
    b = np.ones((3, 3))
    assert np.array_equal(rad.apply({"blue": b})["blue"], b)
    assert np.array_equal(rad.apply({"swir": b})["swir"], b)   # measured, but no reference: untouched
    assert np.all(rad.apply({"red": np.array([[0.0, 255.0]])})["red"] >= 0)
