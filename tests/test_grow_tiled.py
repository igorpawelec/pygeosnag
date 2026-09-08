"""Tiled crown growing: a synthetic scene with grey blobs on green, two points,
the same crowns whether the raster is one window or many small tiles."""
import os

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
fiona = pytest.importorskip("fiona")
pytest.importorskip("pygeoadaptels")
pytest.importorskip("pygeopalette")

from pygeosnag.grow import _tiles, grow_crowns  # noqa: E402


def _scene(tmp_path, size=400):
    """R, G, B, NIR uint8: green canopy with two grey-white blobs (dead crowns)."""
    rng = np.random.default_rng(1)
    r = rng.normal(60, 4, (size, size)); g = rng.normal(95, 4, (size, size)); b = rng.normal(55, 3, (size, size))
    n = rng.normal(140, 6, (size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    blobs = [(100, 120, 9), (300, 260, 12)]
    for cy, cx, rad in blobs:
        d = np.hypot(yy - cy, xx - cx) <= rad
        r[d], g[d], b[d], n[d] = 170, 168, 160, 120
    arr = np.clip(np.stack([r, g, b, n]), 0, 255).astype(np.uint8)
    path = os.path.join(tmp_path, "scene.tif")
    tr = rasterio.transform.from_origin(500000.0, 600000.0, 0.25, 0.25)
    with rasterio.open(path, "w", driver="GTiff", width=size, height=size, count=4, dtype="uint8",
                       crs="EPSG:2180", transform=tr) as dst:
        dst.write(arr)
    pts = os.path.join(tmp_path, "pts.gpkg")
    schema = {"geometry": "Point", "properties": {"id": "int"}}
    with fiona.open(pts, "w", driver="GPKG", schema=schema, crs="EPSG:2180", layer="dead_trees") as dst:
        for i, (cy, cx, _) in enumerate(blobs):
            x, y = tr * (cx + 0.5, cy + 0.5)
            dst.write({"geometry": {"type": "Point", "coordinates": (x, y)}, "properties": {"id": i}})
    return path, pts, blobs


def _crowns(path):
    with fiona.open(path) as f:
        return {ft["properties"]["adaptel_id"]: ft["properties"]["area_m2"] for ft in f}


def test_tiles_cover_the_raster_once():
    cores = _tiles(1000, 700, striped=False, tile=300)
    assert sum((r1 - r0) * (c1 - c0) for r0, r1, c0, c1 in cores) == 1000 * 700
    bands = _tiles(1000, 700, striped=True, tile=300)
    assert all(c0 == 0 and c1 == 700 for _, _, c0, c1 in bands) and bands[-1][1] == 1000


def test_two_blobs_grow_into_two_crowns_whole_or_tiled(tmp_path):
    raster, pts, blobs = _scene(str(tmp_path))
    whole = os.path.join(str(tmp_path), "whole.gpkg")
    tiled = os.path.join(str(tmp_path), "tiled.gpkg")
    labels = os.path.join(str(tmp_path), "labels.tif")
    n1 = grow_crowns(raster, pts, whole, tile=4096, quiet=True)
    n2 = grow_crowns(raster, pts, tiled, tile=128, labels_out=labels, quiet=True)
    assert n1 == 2 and n2 == 2
    a1, a2 = _crowns(whole), _crowns(tiled)
    for i, (_, _, rad) in enumerate(blobs):
        expect = np.pi * rad ** 2 * 0.0625
        assert 0.6 * expect < a1[i] < 1.4 * expect, (i, a1[i], expect)
        assert abs(a1[i] - a2[i]) < 0.5, (i, a1[i], a2[i])            # tie noise at most
    with rasterio.open(labels) as src:
        lab = src.read(1)
        assert src.nodata == -1 and set(np.unique(lab)) == {-1, 0, 1}
        assert (lab >= 0).sum() * 0.0625 == pytest.approx(sum(a2.values()), abs=0.01)
    with fiona.open(tiled) as f:
        props = f.schema["properties"]
        assert f.schema["geometry"] == "MultiPolygon" and {"adaptel_id", "area_m2", "perimeter", "n_parts"} <= set(props)


def test_three_band_cir_is_sniffed_and_grown_on_ndvi(tmp_path, capsys):
    raster, pts, _ = _scene(str(tmp_path))
    cir = os.path.join(str(tmp_path), "cir.tif")
    with rasterio.open(raster) as src:
        arr = src.read()
        prof = src.profile
    prof.update(count=3)
    with rasterio.open(cir, "w", **prof) as dst:
        dst.write(np.stack([arr[3], arr[0], arr[1]]))         # NIR, R, G: band 2 (red) is the darkest
    out = os.path.join(str(tmp_path), "cir_crowns.gpkg")
    assert grow_crowns(cir, pts, out, quiet=False) == 2
    report = capsys.readouterr().out
    assert "mode cir (auto:" in report and "space ndvi_L" in report
