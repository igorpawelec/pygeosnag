"""Raster in, one point per dead tree out.

`detect_array` runs the frozen pipeline on one window held in memory;
`detect` walks a raster in tiles with an overlap, keeps every object whose
centroid falls in a tile's core (the overlap is wider than any crown, so
no tree is written twice), puts the point at the object's area-weighted
centroid -- measured against the reference tops it beats the highest-
scoring and the brightest adaptel, median 0.47 m off the top -- drops the
weaker of two points closer than a crown radius, applies the optional
stand mask, and writes a point layer. The points are what grow_crowns
grows.
"""
import os
import time

import numpy as np

from .features import GSD, MIN_PX, edges_of, feature_names, lch_of, segment_features, to_uint8
from .modes import resolve_mode
from .objects import build_objects, object_features, suppress
from .segment import segment

MIN_VALID_PX = 10_000          # a tile with fewer valid pixels is skipped, as in the research
SUPPRESS_M = 3.0               # two points closer than this: the weaker one goes


def detect_array(bands, valid, mode, forest, transform=None, threshold=0.5, object_forest=None,
                 adaptel_threshold=None):
    """The pipeline on one window.

    Parameters
    ----------
    bands : dict role -> 2-D array, values 0-255 (see features.to_uint8)
    valid : bool array (rows, cols)
    mode : Mode
    forest : fitted segment forest of that mode
    transform : affine.Affine, optional -- centroids in map units if given
    threshold : float, absolute probability cut (0.5 calibrated)
    object_forest : fitted object forest, optional (rgbn)
    adaptel_threshold : float, optional -- overrides the mode's granularity

    Returns
    -------
    dict with seg (labels), prob (per segment), obj_of, n_obj, F (object
    features), centroid (n_obj, 2), p2 (object probability or None),
    obj_raster (int32, 0 = no object, else object id + 1), names, cnt.
    """
    roles = {r: np.asarray(bands[r], np.float32) for r in mode.roles}
    seg = segment(roles, valid, mode, adaptel_threshold)
    lch = lch_of(roles, mode)
    X, lab, cnt, mr, mc = segment_features(seg, roles, valid, lch, mode)
    names = feature_names(mode)
    Xf = np.where(np.isfinite(X), X, 0.0).astype(np.float32)
    big = cnt >= MIN_PX
    p = np.zeros(len(cnt), np.float32)
    if big.any():
        p[big] = forest.predict_proba(Xf[big])[:, 1]
    pred = big & (p >= threshold)
    e = edges_of(seg, valid)
    obj_of, n_obj = build_objects(pred, e)
    area = cnt * GSD * GSD
    if transform is not None:
        xy = np.column_stack([transform.c + (mc + 0.5) * transform.a, transform.f + (mr + 0.5) * transform.e])
    else:
        xy = np.column_stack([mc + 0.5, mr + 0.5])
    F, cent = object_features(obj_of, n_obj, Xf, names, p, area, xy, e)
    p2 = None
    if object_forest is not None and n_obj:
        p2 = object_forest.predict_proba(np.where(np.isfinite(F), F, 0.0))[:, 1]
    obj_raster = np.zeros(seg.shape, np.int32)
    obj_raster[valid] = obj_of[lab] + 1
    return dict(seg=seg, prob=p, obj_of=obj_of, n_obj=n_obj, F=F, centroid=cent, p2=p2,
                obj_raster=obj_raster, names=names, cnt=cnt, mr=mr, mc=mc)


def _tiles(H, W, tile, overlap):
    """(r0, c0, h, w, core_r0, core_r1, core_c0, core_c1) over the raster."""
    step = tile - overlap
    half = overlap // 2
    rows = list(range(0, max(H - overlap, 1), step))
    cols = list(range(0, max(W - overlap, 1), step))
    for i, r0 in enumerate(rows):
        h = min(tile, H - r0)
        cr0 = 0 if i == 0 else r0 + half
        cr1 = H if i == len(rows) - 1 else r0 + tile - half
        for j, c0 in enumerate(cols):
            w = min(tile, W - c0)
            cc0 = 0 if j == 0 else c0 + half
            cc1 = W if j == len(cols) - 1 else c0 + tile - half
            yield r0, c0, h, w, cr0, cr1, cc0, cc1


def _open(raster_path, quiet):
    """The raster, resampled to 0.25 m through a WarpedVRT when it is not."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    src = rasterio.open(raster_path)
    rx, ry = src.res
    if abs(rx - GSD) / GSD > 0.1 or abs(ry - GSD) / GSD > 0.1:
        if not quiet:
            print(f"pygeosnag: pixel {rx:.3f} x {ry:.3f} m, resampling to {GSD} m", flush=True)
        t = src.transform
        new = rasterio.Affine(GSD, t.b, t.c, t.d, -GSD, t.f)
        W = int(round(src.width * rx / GSD))
        H = int(round(src.height * ry / GSD))
        vrt = WarpedVRT(src, transform=new, width=W, height=H, resampling=Resampling.bilinear)
        return src, vrt
    return src, src


def _height_sampler(chm, dtm, dsm, crs, radius_m=3.0):
    """A function xy (n, 2) in the orthophoto's CRS -> canopy height in metres:
    the *maximum* within `radius_m` of the point, NaN where the height
    rasters have no data there. From a CHM, or from a DSM and a DTM (their
    difference); rasters in another CRS are sampled after transforming the
    points. None when no height raster was given.

    The maximum over a neighbourhood, not the value under the point, on
    purpose: an orthophoto is not a true orthophoto and the ALS is not from
    the same day, so a crown in the image and the same crown in the height
    model sit a metre or three apart. The gate only has to answer whether
    anything tall stands near the point -- it separates ground, roads and
    shadow from standing trees and is never evidence about the crown.
    """
    if not chm and not (dtm and dsm):
        return None, []
    import rasterio
    from rasterio.warp import transform as _transform
    paths = [chm] if chm else [dsm, dtm]
    srcs = [rasterio.open(p) for p in paths]

    def grid(src, xy):
        xs, ys = xy[:, 0], xy[:, 1]
        if crs and src.crs and src.crs != crs:
            xs, ys = _transform(crs, src.crs, list(xs), list(ys))
        rows, cols = src.index(xs, ys)
        return np.asarray(rows), np.asarray(cols)

    def read_max(src, rows, cols, r_px):
        out = np.full(len(rows), np.nan)
        for k, (r, c) in enumerate(zip(rows, cols)):
            r0, r1 = max(r - r_px, 0), min(r + r_px + 1, src.height)
            c0, c1 = max(c - r_px, 0), min(c + r_px + 1, src.width)
            if r1 <= r0 or c1 <= c0:
                continue
            from rasterio.windows import Window
            a = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype(float)
            if src.nodata is not None:
                a[a == src.nodata] = np.nan
            if np.isfinite(a).any():
                out[k] = np.nanmax(a)
        return out

    def sample(xy):
        if len(xy) == 0:
            return np.zeros(0)
        if len(srcs) == 1:
            src = srcs[0]
            r_px = int(round(radius_m / abs(src.res[0])))
            rows, cols = grid(src, xy)
            return read_max(src, rows, cols, r_px)
        # DSM - DTM: the terrain under the point, the surface maximum around it
        dsm_src, dtm_src = srcs
        r_px = int(round(radius_m / abs(dsm_src.res[0])))
        rows, cols = grid(dsm_src, xy)
        top = read_max(dsm_src, rows, cols, r_px)
        rows2, cols2 = grid(dtm_src, xy)
        ground = read_max(dtm_src, rows2, cols2, 0)
        return top - ground
    return sample, srcs


def detect(raster_path, out_path, mode=None, bands=None, threshold=0.5, suppress_m=SUPPRESS_M,
           min_area=0.0, stands=None, stand_layer=None, stand_age=10, stand_buffer=-2.0,
           keep_outside=False, chm=None, dtm=None, dsm=None, min_height=3.0, height_radius=3.0,
           keep_low=False, object_stage=True, object_threshold=None, prob_raster=None,
           edge_px=8, tile=2400, overlap=200, model=None, adaptel_threshold=None,
           progress=None, quiet=False):
    """Detect dead trees on a raster and write one point per tree.

    Parameters
    ----------
    raster_path, out_path : str
        Input orthophoto (any GDAL format) and output GeoPackage (layer
        ``dead_trees``: p, p_mean, p_object, area_m2, n_adaptels,
        in_stands, height_m, edge_px, tile, mode, model).
    mode, bands : see modes.resolve_mode.
    threshold : float
        Absolute probability cut per adaptel; 0.5 is calibrated, 0.4-0.6
        the useful range; on a scene the model has not seen, lower.
    suppress_m : float
        Two points closer than this keep only the higher p (3 m).
    min_area : float
        Minimum object area in m2 (0 = none, as calibrated).
    stands, stand_layer, stand_age, stand_buffer, keep_outside : the
        optional stand mask (mask.load_stands); outside points are dropped
        unless keep_outside, then flagged in_stands = 0.
    chm, dtm, dsm, min_height, height_radius, keep_low : the optional
        height gate -- a canopy height model, or a surface and a terrain
        model whose difference is one. The height of a point is the
        maximum within height_radius (3 m) of it, so a crown that sits a
        few metres apart in the image and in the height model still
        counts; a point whose height is below min_height (3 m) is dropped
        unless keep_low; the height is written as height_m either way
        (None where the rasters have no data, never dropped). This
        separates ground, roads and shadow from standing trees and is
        never evidence about the crown; the LP method of Onoszko et al.
        uses a stricter 10 m gate on the value under the pixel.
    object_stage, object_threshold : score the object with the object
        forest (rgbn only) into p_object; drop below object_threshold if set.
    prob_raster : str, optional
        Also write the per-pixel adaptel probability as a GeoTIFF.
    edge_px : int
        Distance to nodata / raster edge written as edge_px (not a filter).
    model : str, optional
        A segment forest .joblib to use instead of the shipped one.
    adaptel_threshold : float, optional
        Override the mode's adaptel granularity (advanced).
    progress : callable(fraction, message) -> bool, optional
        Called after every tile; False cancels (RuntimeError "cancelled").
    """
    from . import assets
    from .mask import inside, load_stands, nodata_distance
    from .vectorize import PointSink, point_record

    t_all = time.time()
    src, ds = _open(raster_path, quiet)
    try:
        m, index = resolve_mode(ds.count, mode, bands)
        if model:
            import joblib
            forest = joblib.load(model)
            model_id = os.path.basename(model)
        else:
            forest = assets.load_forest(m.name, quiet)
            model_id = f"{assets.RELEASE}/{m.name}"
        object_forest = assets.load_forest("objects", quiet) if (object_stage and m.name == "rgbn") else None
        mask_geom = load_stands(stands, stand_layer, min_age=stand_age, buffer_m=stand_buffer,
                                quiet=quiet) if stands else None
        height_at, height_srcs = _height_sampler(chm, dtm, dsm, ds.crs, height_radius)
        if height_at is not None and not quiet:
            print(f"pygeosnag: height gate {min_height:g} m (max within {height_radius:g} m) from "
                  f"{os.path.basename(chm) if chm else 'DSM - DTM'}", flush=True)
        nodata = ds.nodata if ds.nodata is not None else 0
        crs_wkt = ds.crs.to_wkt() if ds.crs else ""
        if os.path.exists(out_path):
            os.remove(out_path)
        sink = PointSink(out_path, crs_wkt)
        prob_dst = None
        if prob_raster:
            import rasterio
            prob_dst = rasterio.open(prob_raster, "w", driver="GTiff", dtype="float32", count=1, width=ds.width,
                                     height=ds.height, crs=ds.crs, transform=ds.transform, nodata=-1.0,
                                     compress="deflate", tiled=True)
        H, W = ds.height, ds.width
        tiles = list(_tiles(H, W, tile, overlap))

        def report(frac, msg):
            if not quiet:
                print(msg, flush=True)
            if progress is not None and progress(frac, msg) is False:
                raise RuntimeError("pygeosnag: cancelled")

        report(0.0, f"pygeosnag: {os.path.basename(raster_path)} {W} x {H} px, mode {m.name}, "
                    f"{len(tiles)} tiles, threshold {threshold}")
        n_total = 0
        for k, (r0, c0, h, w, cr0, cr1, cc0, cc1) in enumerate(tiles):
            from rasterio.windows import Window
            t0 = time.time()
            win = Window(c0, r0, w, h)
            arr = ds.read(window=win).astype(np.float32)
            valid = ((np.isfinite(arr).all(axis=0)) if np.isnan(nodata)
                     else (arr != nodata).all(axis=0) & np.isfinite(arr).all(axis=0))
            tag = f"{r0}_{c0}"
            if valid.sum() < MIN_VALID_PX:
                report((k + 1) / len(tiles), f"  tile {k + 1}/{len(tiles)} ({tag}): nodata, skipped")
                continue
            tf = ds.window_transform(win)
            band_roles = {r: to_uint8(np.where(valid, arr[i], 0.0)) for r, i in index.items()}
            res = detect_array(band_roles, valid, m, forest, tf, threshold, object_forest, adaptel_threshold)
            if prob_dst is not None:
                pr = np.full(valid.shape, -1.0, np.float32)
                lab = res["seg"][valid] - res["seg"][valid].min()
                pr[valid] = res["prob"][lab]
                prob_dst.write(pr[cr0 - r0:cr1 - r0, cc0 - c0:cc1 - c0], 1,
                               window=Window(cc0, cr0, cc1 - cc0, cr1 - cr0))
            n = res["n_obj"]
            if n == 0:
                report((k + 1) / len(tiles), f"  tile {k + 1}/{len(tiles)} ({tag}): {len(res['cnt']):,} adaptels, "
                                             f"0 trees, {time.time() - t0:.0f}s")
                continue
            F, cent, p2 = res["F"], res["centroid"], res["p2"]
            pcol, prow = (~tf) * (cent[:, 0], cent[:, 1])
            pcol, prow = np.asarray(pcol), np.asarray(prow)
            grow, gcol = prow + r0, pcol + c0
            keep = (grow >= cr0) & (grow < cr1) & (gcol >= cc0) & (gcol < cc1)
            keep &= (F[:, 0] >= min_area) & np.isfinite(F).all(axis=1)
            if p2 is not None and object_threshold is not None:
                keep &= p2 >= object_threshold
            in_st = None
            if mask_geom is not None:
                in_st = inside(mask_geom, cent)
                if not keep_outside:
                    keep &= in_st
            heights = None
            if height_at is not None:
                heights = np.full(len(cent), np.nan)
                sel = np.nonzero(keep)[0]
                if len(sel):
                    heights[sel] = height_at(cent[sel])
                if not keep_low:
                    keep &= ~(heights < min_height)       # NaN (no data) is never dropped
            # duplicate suppression among the survivors, by object p_max
            idx = np.nonzero(keep)[0]
            if len(idx) > 1:
                idx = idx[suppress(cent[idx], F[idx, 4], suppress_m)]
            if not len(idx):
                report((k + 1) / len(tiles), f"  tile {k + 1}/{len(tiles)} ({tag}): {len(res['cnt']):,} adaptels, "
                                             f"{n} objects, 0 kept, {time.time() - t0:.0f}s")
                continue
            dist = nodata_distance(valid) if edge_px else None
            recs = []
            for i in idx:
                edge = None
                if dist is not None:
                    rr = int(np.clip(round(prow[i]), 0, h - 1))
                    cc = int(np.clip(round(pcol[i]), 0, w - 1))
                    edge = dist[rr, cc]
                hgt = None if heights is None or not np.isfinite(heights[i]) else float(heights[i])
                recs.append(point_record(cent[i], n_total + len(recs) + 1, F[i], None if p2 is None else p2[i],
                                         None if in_st is None else in_st[i], edge, tag, m.name, model_id, hgt))
            sink.write(recs)
            n_total += len(recs)
            report((k + 1) / len(tiles), f"  tile {k + 1}/{len(tiles)} ({tag}): {len(res['cnt']):,} adaptels, "
                                         f"{n} objects, {len(recs)} trees, {time.time() - t0:.0f}s")
        sink.close()
        if prob_dst is not None:
            prob_dst.close()
        report(1.0, f"pygeosnag: {n_total} dead trees -> {out_path} [{time.time() - t_all:.0f}s]")
        return n_total
    finally:
        for s in locals().get("height_srcs", []) or []:
            try:
                s.close()
            except Exception:
                pass
        if ds is not src:
            ds.close()
        src.close()
