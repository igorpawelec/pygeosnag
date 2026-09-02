"""detect() end to end on a synthetic GeoTIFF with a small real forest, then
grow_crowns() on its points; plus the duplicate suppression rule.

The forest is fitted on the window's own adaptel features with labels from
the planted crowns and dumped with joblib, so no downloaded assets are
needed. Checks: one point per planted crown within a metre, the point
layer's attributes, the probability raster, suppression, and that the
points grow into four crowns of a plausible size.
"""
import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
fiona = pytest.importorskip("fiona")
pytest.importorskip("shapely")
pytest.importorskip("pygeoadaptels")
pytest.importorskip("pygeopalette")
joblib = pytest.importorskip("joblib")
pytest.importorskip("sklearn")

from pygeosnag.detect import detect  # noqa: E402
from pygeosnag.features import MIN_PX, lch_of, segment_features, to_uint8  # noqa: E402
from pygeosnag.grow import grow_crowns  # noqa: E402
from pygeosnag.modes import MODES  # noqa: E402
from pygeosnag.objects import suppress  # noqa: E402
from pygeosnag.segment import segment  # noqa: E402

CENTRES = [(60, 70), (150, 200), (230, 90), (240, 240)]
X0, Y0 = 500000.0, 600000.0


def _write(path, n=300, seed=0):
    rng = np.random.default_rng(seed)
    red = rng.normal(40, 6, (n, n)); grn = rng.normal(55, 6, (n, n)); blu = rng.normal(35, 5, (n, n))
    nir = rng.normal(150, 12, (n, n))
    yy, xx = np.mgrid[:n, :n]
    crowns = np.zeros((n, n), bool)
    for cy, cx in CENTRES:
        d = (yy - cy) ** 2 + (xx - cx) ** 2 <= 8 ** 2
        crowns |= d
        red[d] = 150; grn[d] = 145; blu[d] = 140; nir[d] = 120
    arr = np.stack([red, grn, blu, nir]).clip(0, 255).astype(np.uint8)
    arr[:, :40, :40] = 0
    tf = rasterio.transform.from_origin(X0, Y0, 0.25, 0.25)
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=4, dtype="uint8",
                       crs="EPSG:2180", transform=tf, nodata=0) as dst:
        dst.write(arr)
    return arr, crowns


def _fit_forest(arr, crowns, path):
    from sklearn.ensemble import RandomForestClassifier
    valid = (arr != 0).all(axis=0)
    roles = {r: to_uint8(np.where(valid, arr[i], 0.0)) for r, i in (("red", 0), ("green", 1), ("blue", 2), ("nir", 3))}
    mode = MODES["rgbn"]
    seg = segment(roles, valid, mode)
    X, lab, cnt, mr, mc = segment_features(seg, roles, valid, lch_of(roles, mode), mode)
    frac = np.bincount(lab, weights=crowns[valid].astype(float), minlength=len(cnt)) / np.maximum(cnt, 1)
    big = cnt >= MIN_PX
    rf = RandomForestClassifier(n_estimators=50, random_state=0).fit(
        np.where(np.isfinite(X[big]), X[big], 0.0), frac[big] > 0.5)
    joblib.dump(rf, path)
    return path


def _map(cy, cx):
    return X0 + (cx + 0.5) * 0.25, Y0 - (cy + 0.5) * 0.25


def test_detect_writes_one_point_per_crown_and_grows_them(tmp_path):
    ras = str(tmp_path / "win.tif")
    arr, crowns = _write(ras)
    model = _fit_forest(arr, crowns, str(tmp_path / "rf.joblib"))
    out = str(tmp_path / "trees.gpkg")
    prob = str(tmp_path / "p.tif")
    n = detect(ras, out, mode="rgbn", model=model, object_stage=False, prob_raster=prob, quiet=True)
    assert n == 4, n
    with fiona.open(out, layer="dead_trees") as src:
        pts = [(f["geometry"]["coordinates"], f["properties"]) for f in src]
    assert len(pts) == 4
    for cy, cx in CENTRES:
        x, y = _map(cy, cx)
        assert min(np.hypot(px - x, py - y) for (px, py), _ in pts) < 1.0
    for _, pr in pts:
        assert 0.5 <= pr["p"] <= 1.0 and pr["n_adaptels"] >= 1 and 6 < pr["area_m2"] < 20
        assert pr["mode"] == "rgbn" and pr["model"] == "rf.joblib" and pr["edge_px"] is not None
    with rasterio.open(prob) as src:
        p = src.read(1)
        assert p.shape == (300, 300) and (p[crowns] >= 0.5).mean() > 0.8 and (p[:40, :40] == -1).all()
    crowns_out = str(tmp_path / "crowns.gpkg")
    grow_crowns(ras, out, crowns_out, mode="rgbn", quiet=True)
    from shapely.geometry import shape
    with fiona.open(crowns_out) as src:
        polys = [shape(f["geometry"]) for f in src]
    assert len(polys) == 4
    for g in polys:
        assert 3.0 < g.area < 40.0            # planted discs are pi * 8^2 px * 0.0625 m2 ~ 12.6 m2


def test_suppress_keeps_the_stronger_of_close_points():
    pts = np.array([[0.0, 0.0], [1.0, 0.0], [10.0, 0.0], [10.5, 0.5], [30.0, 30.0]])
    score = np.array([0.6, 0.9, 0.7, 0.5, 0.8])
    keep = suppress(pts, score, 3.0)
    assert keep.tolist() == [False, True, True, False, True]
    assert suppress(pts, score, 0.0).all()
    assert suppress(pts[:1], score[:1], 3.0).tolist() == [True]
