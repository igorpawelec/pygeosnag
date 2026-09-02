"""The whole pipeline on a synthetic window, with a throw-away forest.

No downloaded assets, no raster files: a 300 x 300 four-band image with
dark "canopy", a few bright grey "dead crowns" and a nodata corner, a
forest fitted on the window's own features with labels from the planted
crowns, then detect_array. Checks the plumbing -- segmentation, features,
scoring, merging, object features, the object raster -- not the model.
"""
import numpy as np
import pytest

pytest.importorskip("pygeoadaptels")
pytest.importorskip("pygeopalette")

from pygeosnag.detect import detect_array  # noqa: E402
from pygeosnag.features import MIN_PX, edges_of, feature_names, lch_of, segment_features  # noqa: E402
from pygeosnag.modes import MODES  # noqa: E402
from pygeosnag.segment import segment  # noqa: E402


def synthetic(seed=0, n=300):
    rng = np.random.default_rng(seed)
    red = rng.normal(40, 6, (n, n)); grn = rng.normal(55, 6, (n, n)); blu = rng.normal(35, 5, (n, n))
    nir = rng.normal(150, 12, (n, n))
    crowns = np.zeros((n, n), bool)
    yy, xx = np.mgrid[:n, :n]
    for cy, cx in [(60, 70), (150, 200), (230, 90), (240, 240)]:
        d = (yy - cy) ** 2 + (xx - cx) ** 2 <= 8 ** 2
        crowns |= d
        red[d] = rng.normal(150, 8, d.sum()); grn[d] = rng.normal(145, 8, d.sum())
        blu[d] = rng.normal(140, 8, d.sum()); nir[d] = rng.normal(120, 8, d.sum())
    valid = np.ones((n, n), bool)
    valid[:40, :40] = False
    bands = {k: np.clip(v, 0, 255).astype(np.float32) for k, v in
             dict(red=red, green=grn, blue=blu, nir=nir).items()}
    return bands, valid, crowns


class _Forest:
    """A tiny stand-in with predict_proba: score = fraction of crown pixels."""

    def __init__(self, score):
        self.score = score

    def predict_proba(self, X):
        s = self.score[:len(X)] if len(X) == len(self.score) else np.zeros(len(X))
        return np.column_stack([1 - s, s])


def test_pipeline_finds_the_planted_crowns():
    bands, valid, crowns = synthetic()
    mode = MODES["rgbn"]
    seg = segment(bands, valid, mode)
    assert seg.shape == valid.shape and (seg[~valid] == -1).all() and seg[valid].min() >= 0
    lch = lch_of(bands, mode)
    X, lab, cnt, mr, mc = segment_features(seg, bands, valid, lch, mode)
    assert X.shape[1] == len(feature_names(mode)) and len(cnt) == lab.max() + 1
    # a "forest" that knows the truth: per-segment crown fraction, restricted to big segments
    frac = np.bincount(lab, weights=crowns[valid].astype(float), minlength=len(cnt)) / np.maximum(cnt, 1)
    big = cnt >= MIN_PX
    forest = _Forest(frac[big])          # detect_array scores only the big segments, in order
    res = detect_array(bands, valid, mode, forest, transform=None, threshold=0.5)
    assert res["n_obj"] == 4, res["n_obj"]
    F, cent = res["F"], res["centroid"]
    assert F.shape[0] == 4 and cent.shape == (4, 2)
    # every planted crown centre has an object centroid within a few pixels (x = col + .5, y = row + .5)
    for cy, cx in [(60, 70), (150, 200), (230, 90), (240, 240)]:
        d = np.hypot(cent[:, 0] - (cx + 0.5), cent[:, 1] - (cy + 0.5)).min()
        assert d < 4, d
    # object areas about the planted disc (pi * 8^2 px * 0.0625 m2)
    assert np.all((F[:, 0] > 6) & (F[:, 0] < 20))
    obj = res["obj_raster"]
    assert obj.max() == 4 and (obj[~valid] == 0).all()
    e = edges_of(seg, valid)
    assert e.ndim == 2 and e.shape[1] == 2 and (e[:, 0] < e[:, 1]).all()


def test_no_detection_gives_empty_objects():
    bands, valid, _ = synthetic(seed=1)
    mode = MODES["rgb"]
    seg = segment(bands, valid, mode)
    lch = lch_of(bands, mode)
    X, lab, cnt, *_ = segment_features(seg, bands, valid, lch, mode)
    forest = _Forest(np.zeros(int((cnt >= MIN_PX).sum())))
    res = detect_array(bands, valid, mode, forest, threshold=0.5)
    assert res["n_obj"] == 0 and res["F"].shape[0] == 0 and res["obj_raster"].max() == 0
