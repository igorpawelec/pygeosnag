"""Teach the detector a new scene from a few labelled windows.

A forest trained on seven pine sites misses what it has never seen: on a
mountain spruce plot the bleached white snags sat at the 90th-95th
percentile of the training dead crowns in lightness and contrast, and
scored 0.23. Adding one labelled window of such a scene to the training
table and refitting is the research protocol of report section 14, where
three windows recovered a site from F1 0.24 to 0.67.

Labels are points: dead trees (positives) and, optionally, objects the
reviewer rejected (hard negatives). A point labels the adaptel under it;
the neighbours of every positive and a 1:10 sample of everything else
become background, as in the training table. The new rows are appended
to the pooled feature table of the mode with a sample weight, and the
forest is refitted with the same settings as the shipped one.
"""
import json
import os
import time

import numpy as np

from .features import GSD, MIN_PX, edges_of, feature_names, lch_of, segment_features, to_uint8
from .modes import resolve_mode
from .segment import segment

RF_KW = dict(n_estimators=200, min_samples_leaf=5, max_samples=0.4,
             class_weight="balanced_subsample", random_state=0, n_jobs=-1)
NEG_K = 10                       # background subsample, as in the training table


def _read_points(path, layer=None):
    """Point coordinates of a vector file; accepts QGIS's ``path|layername=x``."""
    import fiona
    if "|" in str(path):
        path, _, rest = str(path).partition("|")
        for part in rest.split("|"):
            if part.startswith("layername="):
                layer = part[len("layername="):]
    with fiona.open(path, layer=layer) as src:
        return np.array([f["geometry"]["coordinates"][:2] for f in src], float)


def label_window(raster_path, positives, negatives=None, mode=None, bands=None, quiet=False, seed=0):
    """Feature rows and labels of one raster from point labels.

    Returns X (float32), y (bool), and a dict of counts. Rasters larger
    than one tile are processed whole; keep them to a few thousand pixels
    a side (the windows of the research were 2400 px).
    """
    import rasterio
    from rasterio.windows import Window
    with rasterio.open(raster_path) as src:
        m, index = resolve_mode(src.count, mode, bands)
        arr = src.read().astype(np.float32)
        nodata = src.nodata if src.nodata is not None else 0
        valid = (arr != nodata).all(axis=0) & np.isfinite(arr).all(axis=0)
        tf = src.transform
        roles = {r: to_uint8(np.where(valid, arr[i], 0.0)) for r, i in index.items()}
        seg = segment(roles, valid, m)
        lch = lch_of(roles, m)
        X, lab, cnt, mr, mc = segment_features(seg, roles, valid, lch, m)
        base = seg[valid].min()
        n_lab = len(cnt)

        def under(points):
            """Re-based label of the adaptel under each point (or -1)."""
            out = -np.ones(len(points), np.int64)
            if not len(points):
                return out
            rows, cols = src.index(points[:, 0], points[:, 1])
            rows, cols = np.asarray(rows), np.asarray(cols)
            ok = (rows >= 0) & (rows < src.height) & (cols >= 0) & (cols < src.width)
            ok[ok] &= valid[rows[ok], cols[ok]]
            out[ok] = seg[rows[ok], cols[ok]].astype(np.int64) - base
            return out

        pos_lab = under(positives)
        neg_lab = under(negatives) if negatives is not None and len(negatives) else np.zeros(0, np.int64)
        big = cnt >= MIN_PX
        pos = np.zeros(n_lab, bool)
        pos[pos_lab[pos_lab >= 0]] = True
        pos &= big
        hard = np.zeros(n_lab, bool)
        hard[neg_lab[neg_lab >= 0]] = True
        hard &= ~pos
        e = edges_of(seg, valid)
        near = np.zeros(n_lab, bool)
        pe = pos[e[:, 0]] | pos[e[:, 1]]
        near[e[pe, 0]] = True
        near[e[pe, 1]] = True
        rng = np.random.default_rng(seed)
        sel = big & (pos | near | hard | (rng.random(n_lab) < 1.0 / NEG_K))
        Xs = np.where(np.isfinite(X[sel]), X[sel], 0.0).astype(np.float32)
        counts = dict(segments=int(n_lab), positives=int(pos.sum()), hard_negatives=int(hard.sum()),
                      rows=int(sel.sum()), points_outside=int((pos_lab < 0).sum()), mode=m.name)
        if not quiet:
            print(f"pygeosnag: {os.path.basename(raster_path)}: {counts['segments']:,} adaptels, "
                  f"{counts['positives']} positive, {counts['hard_negatives']} hard negative, "
                  f"{counts['rows']:,} rows", flush=True)
        return Xs, pos[sel], counts


def adapt(windows, out_model, mode=None, bands=None, weight=1.0, quiet=False):
    """Refit the forest of a mode with extra labelled windows.

    Parameters
    ----------
    windows : list of (raster_path, positives_path, negatives_path or None)
    out_model : path of the joblib to write; a .json next to it records
        what went in
    mode, bands : as in detect; every window must be in the same mode
    weight : sample weight of the new rows (1 = like the training table)
    """
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from . import assets

    t0 = time.time()
    Xn, yn, info = [], [], []
    for raster_path, pos_path, neg_path in windows:
        P = _read_points(pos_path)
        N = _read_points(neg_path) if neg_path else None
        X, y, counts = label_window(raster_path, P, N, mode, bands, quiet)
        Xn.append(X)
        yn.append(y)
        counts["raster"] = os.path.abspath(raster_path)
        info.append(counts)
    m_name = info[0]["mode"]
    if any(c["mode"] != m_name for c in info):
        raise ValueError("all windows must be in the same band mode")
    Xn, yn = np.vstack(Xn), np.concatenate(yn)
    X0, y0, _ = assets.feature_table(m_name, quiet)
    X = np.vstack([X0, Xn])
    y = np.concatenate([y0, yn])
    w = np.concatenate([np.ones(len(y0), np.float32), np.full(len(yn), float(weight), np.float32)])
    if not quiet:
        print(f"pygeosnag: refitting the {m_name} forest on {len(y0):,} + {len(yn):,} rows "
              f"({int(yn.sum())} new positives, weight {weight:g}) ...", flush=True)
    rf = RandomForestClassifier(**RF_KW).fit(X, y, sample_weight=w)
    joblib.dump(rf, out_model, compress=3)
    meta = dict(mode=m_name, base_release=assets.RELEASE, features=feature_names(assets_mode(m_name)),
                weight=weight, windows=info, rows_total=int(len(y)), positives_total=int(y.sum()),
                seconds=round(time.time() - t0))
    with open(os.path.splitext(out_model)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    if not quiet:
        print(f"pygeosnag: adapted forest -> {out_model} [{time.time() - t0:.0f}s]", flush=True)
    return out_model


def assets_mode(name):
    from .modes import MODES
    return MODES[name]
