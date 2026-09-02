"""From scored adaptels to objects: merge adjacent detections, describe
the merged object, and (optionally) score it with the second forest.

An object is a set of adjacent adaptels whose probability passed the
threshold. Its features: area, number of segments, elongation (segment
centroids treated as discs), the probability statistics, the area-
weighted mean of the segment features, and the ring of neighbouring
segments (their NDVI or, without NIR, NDGR, their lightness, their
count). These are the features the object forest was trained on.
"""
import numpy as np

OBJ_BASE = ["pow", "nseg", "elong", "elong_seg", "s_max", "s_mean", "s_min",
            "ring_ndvi", "ring_L", "ring_n"]


def object_feature_names(names):
    return OBJ_BASE + [f"obj.{n}" for n in names]


def suppress(points, score, radius):
    """Keep the higher-scoring point of any two closer than `radius` (map units).

    A dead crown at p >= 0.5 sometimes comes out as two or three bright
    pieces; the reference marks one top. Measured on seven sites, 3 m
    suppression raised F1 from 0.424 to 0.435 at 2 points of recall.
    Returns a boolean keep mask.
    """
    n = len(points)
    keep = np.ones(n, bool)
    if radius <= 0 or n < 2:
        return keep
    from scipy.spatial import cKDTree
    tree = cKDTree(points)
    taken = np.zeros(n, bool)
    for i in np.argsort(-np.asarray(score)):
        if taken[i]:
            keep[i] = False
            continue
        for j in tree.query_ball_point(points[i], radius):
            if j != i and not taken[j]:
                taken[j] = True
        taken[i] = True
    return keep


class UnionFind:
    def __init__(self, n):
        self.p = np.arange(n)

    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def build_objects(pred, edges):
    """Union-find over predicted segments -> object id per segment (-1 outside)."""
    n = len(pred)
    obj_of = -np.ones(n, np.int64)
    idx = np.nonzero(pred)[0]
    if not len(idx):
        return obj_of, 0
    uf = UnionFind(n)
    e = edges
    for a, b in e[pred[e[:, 0]] & pred[e[:, 1]]]:
        uf.union(int(a), int(b))
    root = np.array([uf.find(int(i)) for i in idx])
    _, inv = np.unique(root, return_inverse=True)
    obj_of[idx] = inv
    return obj_of, int(inv.max()) + 1


def object_features(obj_of, n_obj, X, names, p, area, xy, edges):
    """Object feature table, centroids -- see module docstring.

    Parameters
    ----------
    obj_of : int array per segment, -1 outside objects
    n_obj : int
    X : float32 (n_segments, n_features), non-finite already replaced
    names : feature names of X
    p : float array per segment, first-stage probability
    area : float array per segment, m2
    xy : float (n_segments, 2) segment centroids in map units
    edges : int (m, 2) adjacencies
    """
    i_ndvi = names.index("sr.NDVI") if "sr.NDVI" in names else names.index("sr.NDGR")
    i_L, i_el = names.index("sr.L"), names.index("wydluzenie")
    nf = len(object_feature_names(names))
    if n_obj == 0:
        return np.zeros((0, nf), np.float32), np.zeros((0, 2))
    idx = np.nonzero(obj_of >= 0)[0]
    inv = obj_of[idx]
    n = n_obj
    w = area[idx].astype(np.float64)
    W = np.bincount(inv, weights=w, minlength=n)
    cx = np.bincount(inv, weights=xy[idx, 0] * w, minlength=n) / W
    cy = np.bincount(inv, weights=xy[idx, 1] * w, minlength=n) / W
    dx, dy = xy[idx, 0] - cx[inv], xy[idx, 1] - cy[inv]
    disc = w * w / (4 * np.pi)
    sxx = np.bincount(inv, weights=w * dx * dx + disc, minlength=n) / W
    syy = np.bincount(inv, weights=w * dy * dy + disc, minlength=n) / W
    sxy = np.bincount(inv, weights=w * dx * dy, minlength=n) / W
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    disc2 = np.sqrt(np.maximum(tr * tr / 4 - det, 0))
    l1, l2 = tr / 2 + disc2, np.maximum(tr / 2 - disc2, 1e-9)
    elong = np.sqrt(l1 / l2)
    Xd = X.astype(np.float64)
    objX = np.column_stack([np.bincount(inv, weights=w * Xd[idx, k], minlength=n) / W
                            for k in range(Xd.shape[1])])
    ps = p[idx].astype(np.float64)
    s_max = np.full(n, -np.inf)
    np.maximum.at(s_max, inv, ps)
    s_min = np.full(n, np.inf)
    np.minimum.at(s_min, inv, ps)
    s_mean = np.bincount(inv, weights=w * ps, minlength=n) / W
    nseg = np.bincount(inv, minlength=n).astype(np.float64)
    e = edges
    oa, ob = obj_of[e[:, 0]], obj_of[e[:, 1]]
    ring_o = np.concatenate([oa[(oa >= 0) & (ob < 0)], ob[(ob >= 0) & (oa < 0)]])
    ring_s = np.concatenate([e[(oa >= 0) & (ob < 0), 1], e[(ob >= 0) & (oa < 0), 0]])
    rw = area[ring_s].astype(np.float64)
    RW = np.bincount(ring_o, weights=rw, minlength=n)
    ring_n = np.bincount(ring_o, minlength=n).astype(np.float64)
    ring_ndvi = np.where(RW > 0, np.bincount(ring_o, weights=rw * Xd[ring_s, i_ndvi], minlength=n)
                         / np.maximum(RW, 1e-9), 0.0)
    ring_L = np.where(RW > 0, np.bincount(ring_o, weights=rw * Xd[ring_s, i_L], minlength=n)
                      / np.maximum(RW, 1e-9), 0.0)
    F = np.column_stack([W, nseg, elong, objX[:, i_el], s_max, s_mean, s_min,
                         ring_ndvi, ring_L, ring_n, objX]).astype(np.float32)
    return F, np.column_stack([cx, cy])
