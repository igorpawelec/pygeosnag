"""Union-find merging, object features and the tile grid, on synthetic data."""
import numpy as np
import pytest

from pygeosnag.detect import _tiles
from pygeosnag.objects import OBJ_BASE, build_objects, object_feature_names, object_features


def test_build_objects_merges_only_adjacent_predictions():
    # segments 0-1-2 in a chain, 3 isolated, 4 predicted but adjacent only to unpredicted 5
    edges = np.array([[0, 1], [1, 2], [2, 5], [4, 5], [3, 5]])
    pred = np.array([True, True, True, True, True, False])
    obj_of, n = build_objects(pred, edges)
    assert n == 3
    assert obj_of[0] == obj_of[1] == obj_of[2]
    assert obj_of[3] != obj_of[0] and obj_of[4] != obj_of[0] and obj_of[3] != obj_of[4]
    assert obj_of[5] == -1


def test_build_objects_empty():
    obj_of, n = build_objects(np.zeros(4, bool), np.array([[0, 1]]))
    assert n == 0 and (obj_of == -1).all()


def test_object_features_shapes_and_ring():
    names = ["sr.NDVI", "sr.L", "wydluzenie", "pow.m2"]
    X = np.array([[0.1, 50, 1.0, 1.0],
                  [0.2, 60, 1.5, 2.0],
                  [0.8, 30, 1.2, 1.0],     # neighbour, live canopy
                  [0.7, 20, 1.1, 3.0]], np.float32)
    edges = np.array([[0, 1], [1, 2], [0, 3]])
    pred = np.array([True, True, False, False])
    area = np.array([1.0, 2.0, 1.0, 3.0])
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [0.0, 1.0]])
    p = np.array([0.9, 0.6, 0.1, 0.2])
    obj_of, n = build_objects(pred, edges)
    F, cent = object_features(obj_of, n, X, names, p, area, xy, edges)
    assert n == 1 and F.shape == (1, len(object_feature_names(names))) and cent.shape == (1, 2)
    row = dict(zip(object_feature_names(names), F[0]))
    assert row["pow"] == pytest.approx(3.0)
    assert row["nseg"] == 2
    assert row["s_max"] == pytest.approx(0.9) and row["s_min"] == pytest.approx(0.6)
    assert row["s_mean"] == pytest.approx((0.9 * 1 + 0.6 * 2) / 3)
    # ring: segments 2 (area 1, ndvi .8) and 3 (area 3, ndvi .7)
    assert row["ring_n"] == 2
    assert row["ring_ndvi"] == pytest.approx((0.8 * 1 + 0.7 * 3) / 4)
    assert row["ring_L"] == pytest.approx((30 * 1 + 20 * 3) / 4)
    assert cent[0, 0] == pytest.approx((0 * 1 + 1 * 2) / 3)
    assert row["elong"] >= 1.0
    assert OBJ_BASE[0] == "pow"


def test_tiles_cover_every_pixel_exactly_once_in_cores():
    H, W, tile, ov = 5000, 3700, 2400, 200
    cover = np.zeros((H, W), np.int32)
    for r0, c0, h, w, cr0, cr1, cc0, cc1 in _tiles(H, W, tile, ov):
        assert r0 + h <= H and c0 + w <= W
        assert r0 <= cr0 < cr1 <= r0 + h and c0 <= cc0 < cc1 <= c0 + w
        cover[cr0:cr1, cc0:cc1] += 1
    assert (cover == 1).all()


def test_tiles_small_raster_is_one_tile():
    tiles = list(_tiles(500, 300, 2400, 200))
    assert len(tiles) == 1
    r0, c0, h, w, cr0, cr1, cc0, cc1 = tiles[0]
    assert (r0, c0, h, w) == (0, 0, 500, 300) and (cr0, cr1, cc0, cc1) == (0, 500, 0, 300)
