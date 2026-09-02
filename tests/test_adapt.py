"""Labelling a window from points: positives under points, hard negatives,
neighbours and the 1:10 background, on a synthetic GeoTIFF."""
import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
pytest.importorskip("pygeoadaptels")
pytest.importorskip("pygeopalette")

from pygeosnag.adapt import label_window  # noqa: E402
from pygeosnag.features import feature_names  # noqa: E402
from pygeosnag.modes import MODES  # noqa: E402


def _write(path, n=300, seed=0):
    rng = np.random.default_rng(seed)
    red = rng.normal(40, 6, (n, n)); grn = rng.normal(55, 6, (n, n)); blu = rng.normal(35, 5, (n, n))
    nir = rng.normal(150, 12, (n, n))
    yy, xx = np.mgrid[:n, :n]
    centres = [(60, 70), (150, 200), (230, 90)]
    for cy, cx in centres:
        d = (yy - cy) ** 2 + (xx - cx) ** 2 <= 8 ** 2
        red[d] = 150; grn[d] = 145; blu[d] = 140; nir[d] = 120
    arr = np.stack([red, grn, blu, nir]).clip(0, 255).astype(np.uint8)
    arr[:, :30, :30] = 0
    tf = rasterio.transform.from_origin(500000.0, 600000.0, 0.25, 0.25)
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=4, dtype="uint8",
                       crs="EPSG:2180", transform=tf, nodata=0) as dst:
        dst.write(arr)
    pts = np.array([[500000.0 + (cx + 0.5) * 0.25, 600000.0 - (cy + 0.5) * 0.25] for cy, cx in centres])
    return pts, tf


def test_label_window_marks_the_adaptel_under_each_point(tmp_path):
    path = str(tmp_path / "win.tif")
    pts, tf = _write(path)
    neg = np.array([[500000.0 + 20 * 0.25, 600000.0 - 250 * 0.25],      # inside, live canopy
                    [500000.0 + 5 * 0.25, 600000.0 - 5 * 0.25],          # nodata corner -> ignored
                    [499000.0, 600000.0]])                                # outside the raster -> ignored
    X, y, counts = label_window(path, pts, neg, mode="rgbn", quiet=True)
    assert counts["mode"] == "rgbn" and X.shape[1] == len(feature_names(MODES["rgbn"]))
    assert counts["positives"] == 3 and y.sum() == 3
    assert counts["hard_negatives"] == 1
    assert counts["points_outside"] == 0
    # background: neighbours of the 3 positives plus about a tenth of the rest
    assert counts["rows"] > 3 + 1 and counts["rows"] < counts["segments"] * 0.5
    assert len(X) == len(y) == counts["rows"] and np.isfinite(X).all()


def test_label_window_rgb_mode_drops_nir(tmp_path):
    path = str(tmp_path / "win.tif")
    pts, _ = _write(path, seed=1)
    X, y, counts = label_window(path, pts, None, mode="rgb", quiet=True)
    assert X.shape[1] == 17 and counts["hard_negatives"] == 0 and y.sum() == 3
