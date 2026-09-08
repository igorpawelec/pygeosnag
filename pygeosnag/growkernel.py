"""Seeded growing where a pixel can only go to a seed within reach.

pygeoadaptels' `grow_seeds` is one global image-foresting-transform partition
with every seed, cut afterwards by the tolerance and the radius. In a dense
cluster of dead trees that is the wrong order: a pixel of one crown is won
by a farther seed with a slightly better minimax path, the radius cut then
drops it, and the near seed never gets it back. Measured on Gizycko
(6460 verified crowns, 80_grow_bench 2026-09-08): the seed of a crown kept
39% of its own pixels whatever the tolerance or radius; no feature space
moved the median IoU above 0.49.

`ift_within_reach` runs the same seed-anchored minimax IFT, but a seed
only propagates to pixels within `max_radius` of itself and reachable
under `max_cost`; the pixel goes to the eligible seed with the lowest
path cost. The cuts are inside the growth, so nothing is won and dropped.
"""
import numpy as np
from numba import njit

_NB = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


@njit(cache=True)
def _push(h_cost, h_pix, h_seed, size, cost, pix, seed):
    i = size
    h_cost[i] = cost
    h_pix[i] = pix
    h_seed[i] = seed
    while i > 0:
        p = (i - 1) // 2
        if h_cost[p] <= h_cost[i]:
            break
        h_cost[p], h_cost[i] = h_cost[i], h_cost[p]
        h_pix[p], h_pix[i] = h_pix[i], h_pix[p]
        h_seed[p], h_seed[i] = h_seed[i], h_seed[p]
        i = p
    return size + 1


@njit(cache=True)
def _pop(h_cost, h_pix, h_seed, size):
    cost, pix, seed = h_cost[0], h_pix[0], h_seed[0]
    size -= 1
    h_cost[0], h_pix[0], h_seed[0] = h_cost[size], h_pix[size], h_seed[size]
    i = 0
    while True:
        l, r = 2 * i + 1, 2 * i + 2
        m = i
        if l < size and h_cost[l] < h_cost[m]:
            m = l
        if r < size and h_cost[r] < h_cost[m]:
            m = r
        if m == i:
            break
        h_cost[m], h_cost[i] = h_cost[i], h_cost[m]
        h_pix[m], h_pix[i] = h_pix[i], h_pix[m]
        h_seed[m], h_seed[i] = h_seed[i], h_seed[m]
        i = m
    return cost, pix, seed, size


@njit(cache=True)
def ift_within_reach(feat, valid, seed_r, seed_c, weights, max_cost, max_radius):
    """feat (bands, H, W) float32; valid (H, W) uint8 1 = usable; seeds as row/col
    arrays; weights per band. Returns labels (H, W) int32, -1 unassigned."""
    nb, H, W = feat.shape
    n = H * W
    labels = np.full(n, -1, np.int32)
    best = np.full(n, np.inf)
    done = np.zeros(n, np.uint8)
    ns = seed_r.shape[0]
    cap = max(1024, ns * 4)
    h_cost = np.empty(cap)
    h_pix = np.empty(cap, np.int64)
    h_seed = np.empty(cap, np.int32)
    size = 0
    r2 = max_radius * max_radius
    for s in range(ns):
        p = seed_r[s] * W + seed_c[s]
        if valid[seed_r[s], seed_c[s]] == 0:
            continue
        if 0.0 < best[p]:
            best[p] = 0.0
            labels[p] = s
            size = _push(h_cost, h_pix, h_seed, size, 0.0, p, s)
    while size > 0:
        cost, p, s, size = _pop(h_cost, h_pix, h_seed, size)
        if done[p] == 1 or cost > best[p]:
            continue
        done[p] = 1
        labels[p] = s
        pr, pc = p // W, p % W
        sr, sc = seed_r[s], seed_c[s]
        for k in range(8):
            nr = pr + _NB_R[k]
            nc = pc + _NB_C[k]
            if nr < 0 or nr >= H or nc < 0 or nc >= W:
                continue
            q = nr * W + nc
            if done[q] == 1 or valid[nr, nc] == 0:
                continue
            dr = nr - sr
            dc = nc - sc
            if dr * dr + dc * dc > r2:
                continue
            d2 = 0.0
            for b in range(nb):
                diff = (feat[b, nr, nc] - feat[b, sr, sc]) * weights[b]
                d2 += diff * diff
            d = np.sqrt(d2)
            nd = cost if cost > d else d
            if nd > max_cost:
                continue
            if nd < best[q]:
                best[q] = nd
                if size >= cap:
                    cap2 = cap * 2
                    nc_cost = np.empty(cap2)
                    nc_pix = np.empty(cap2, np.int64)
                    nc_seed = np.empty(cap2, np.int32)
                    nc_cost[:size] = h_cost[:size]
                    nc_pix[:size] = h_pix[:size]
                    nc_seed[:size] = h_seed[:size]
                    h_cost, h_pix, h_seed, cap = nc_cost, nc_pix, nc_seed, cap2
                size = _push(h_cost, h_pix, h_seed, size, nd, q, s)
    return labels.reshape(H, W)


_NB_R = np.array([d[0] for d in _NB], np.int64)
_NB_C = np.array([d[1] for d in _NB], np.int64)


def grow_within_reach(data, seeds, mask=None, max_cost=15.0, band_weights=None, max_radius=20, fill_holes=True):
    """Same contract as pygeoadaptels.grow.grow_seeds (data (bands, rows, cols) or (rows, cols),
    seeds (n, 2) row/col, mask nonzero = nodata) with the within-reach rule."""
    data = np.asarray(data, np.float32)
    if data.ndim == 2:
        data = data[None]
    nb, H, W = data.shape
    valid = np.isfinite(data).all(axis=0)
    if mask is not None:
        valid &= (np.asarray(mask) == 0)
    seeds = np.asarray(seeds, np.int64)
    w = np.ones(nb) if band_weights is None else np.asarray(band_weights, np.float64)
    if w.shape != (nb,):
        raise ValueError(f"band_weights must have {nb} entries")
    labels = ift_within_reach(np.ascontiguousarray(data), valid.astype(np.uint8), seeds[:, 0].astype(np.int64),
                              seeds[:, 1].astype(np.int64), w, float(max_cost), float(max_radius))
    if fill_holes:
        from pygeoadaptels.grow import _fill_holes
        labels = _fill_holes(labels, (~valid).astype(np.uint8))
    return labels
