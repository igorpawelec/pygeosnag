"""The within-reach kernel: a pixel goes only to a seed within the radius and under the
tolerance, the nearest-cost eligible seed wins, nodata is never entered."""
import numpy as np
import pytest

pytest.importorskip("numba")

from pygeosnag.growkernel import grow_within_reach  # noqa: E402


def _blobs():
    img = np.full((60, 60), 10.0, np.float32)
    img[10:22, 10:22] = 100.0                 # blob A, 12 x 12
    img[30:50, 30:50] = 100.0                 # blob B, 20 x 20, touches A's radius nowhere
    return img


def test_two_blobs_two_crowns_within_tolerance_and_radius():
    img = _blobs()
    seeds = np.array([[15, 15], [40, 40]])
    lab = grow_within_reach(img, seeds, max_cost=5.0, max_radius=20, fill_holes=False)
    assert (lab[10:22, 10:22] == 0).all() and (lab[30:50, 30:50] == 1).all()
    assert (lab[img < 50] == -1).all()        # background is 90 units away: never taken


def test_radius_caps_the_region_even_when_the_tolerance_would_not():
    img = np.full((60, 60), 100.0, np.float32)   # one flat field
    lab = grow_within_reach(img, np.array([[30, 30]]), max_cost=5.0, max_radius=5, fill_holes=False)
    yy, xx = np.mgrid[0:60, 0:60]
    d = np.hypot(yy - 30, xx - 30)
    assert (lab[d <= 5] == 0).all() and (lab[d > 5.01] == -1).all()


def test_near_seed_keeps_its_pixels_and_nodata_blocks():
    img = np.full((40, 40), 100.0, np.float32)
    mask = np.zeros((40, 40), np.uint8)
    mask[:, 20] = 1                            # a nodata wall down the middle
    lab = grow_within_reach(img, np.array([[20, 5], [20, 35]]), mask=mask, max_cost=5.0, max_radius=30, fill_holes=False)
    assert (lab[:, :20] == 0).all() and (lab[:, 21:] == 1).all() and (lab[:, 20] == -1).all()


def test_band_weights_and_tolerance_act_on_the_seed_distance():
    img = np.zeros((2, 20, 20), np.float32)
    img[1, :, 10:] = 8.0                       # second band steps by 8 on the right half
    lab_w1 = grow_within_reach(img, np.array([[10, 2]]), max_cost=10.0, band_weights=[1.0, 1.0], max_radius=30, fill_holes=False)
    lab_w2 = grow_within_reach(img, np.array([[10, 2]]), max_cost=10.0, band_weights=[1.0, 2.0], max_radius=30, fill_holes=False)
    assert (lab_w1[:, 10:] == 0).all()         # 8 < 10: crossed
    assert (lab_w2[:, 10:] == -1).all()        # 16 > 10: stopped
