"""The height gate: a synthetic CHM drops the planted crown that stands on
low ground, keep_low keeps it flagged, and a DSM/DTM pair works like a CHM."""
import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
fiona = pytest.importorskip("fiona")
pytest.importorskip("pygeoadaptels")
pytest.importorskip("pygeopalette")
joblib = pytest.importorskip("joblib")
pytest.importorskip("sklearn")

from pygeosnag.detect import detect  # noqa: E402

from test_points_output import X0, Y0, _fit_forest, _write  # noqa: E402


def _height_rasters(tmp_path, n=300):
    """CHM 20 m over three crowns, 1 m over the fourth (240, 240); also DSM/DTM."""
    chm = np.full((n, n), 20.0, np.float32)
    chm[200:, 200:] = 1.0                      # the south-east crown stands on low ground
    chm[:40, :40] = -9999.0                    # nodata corner
    tf = rasterio.transform.from_origin(X0, Y0, 0.25, 0.25)
    paths = {}
    for name, arr in (("chm", chm), ("dsm", chm + 100.0), ("dtm", np.full((n, n), 100.0, np.float32))):
        p = str(tmp_path / f"{name}.tif")
        with rasterio.open(p, "w", driver="GTiff", width=n, height=n, count=1, dtype="float32",
                           crs="EPSG:2180", transform=tf, nodata=-9999.0) as dst:
            dst.write(arr, 1)
        paths[name] = p
    return paths


def _points(path):
    with fiona.open(path, layer="dead_trees") as src:
        return [(f["geometry"]["coordinates"], f["properties"]) for f in src]


def test_chm_gate_drops_the_low_crown_and_keep_low_flags_it(tmp_path):
    ras = str(tmp_path / "win.tif")
    arr, crowns = _write(ras)
    model = _fit_forest(arr, crowns, str(tmp_path / "rf.joblib"))
    h = _height_rasters(tmp_path)
    n = detect(ras, str(tmp_path / "gate.gpkg"), mode="rgbn", model=model, object_stage=False,
               chm=h["chm"], min_height=5.0, quiet=True)
    assert n == 3
    pts = _points(str(tmp_path / "gate.gpkg"))
    low_x, low_y = X0 + (240 + 0.5) * 0.25, Y0 - (240 + 0.5) * 0.25
    assert all(np.hypot(x - low_x, y - low_y) > 2.0 for (x, y), _ in pts)
    assert all(abs(pr["height_m"] - 20.0) < 0.01 for _, pr in pts)
    n2 = detect(ras, str(tmp_path / "keep.gpkg"), mode="rgbn", model=model, object_stage=False,
                chm=h["chm"], min_height=5.0, keep_low=True, quiet=True)
    assert n2 == 4
    heights = sorted(pr["height_m"] for _, pr in _points(str(tmp_path / "keep.gpkg")))
    assert abs(heights[0] - 1.0) < 0.01 and all(abs(v - 20.0) < 0.01 for v in heights[1:])


def test_dsm_minus_dtm_is_a_chm(tmp_path):
    ras = str(tmp_path / "win.tif")
    arr, crowns = _write(ras, seed=3)
    model = _fit_forest(arr, crowns, str(tmp_path / "rf.joblib"))
    h = _height_rasters(tmp_path)
    n = detect(ras, str(tmp_path / "pair.gpkg"), mode="rgbn", model=model, object_stage=False,
               dsm=h["dsm"], dtm=h["dtm"], min_height=5.0, quiet=True)
    assert n == 3
    assert all(abs(pr["height_m"] - 20.0) < 0.01 for _, pr in _points(str(tmp_path / "pair.gpkg")))


def test_no_height_raster_means_no_gate(tmp_path):
    ras = str(tmp_path / "win.tif")
    arr, crowns = _write(ras, seed=4)
    model = _fit_forest(arr, crowns, str(tmp_path / "rf.joblib"))
    n = detect(ras, str(tmp_path / "none.gpkg"), mode="rgbn", model=model, object_stage=False, quiet=True)
    assert n == 4
    assert all(pr["height_m"] is None for _, pr in _points(str(tmp_path / "none.gpkg")))
