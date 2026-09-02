"""Raster in, dead-crown polygons out.

`detect_array` runs the frozen pipeline on one window held in memory;
`detect` walks a raster in tiles with an overlap, keeps every object
whose centroid falls in a tile's core (the overlap is wider than any
crown, so no object is cut or written twice), applies the optional stand
mask and object forest, and writes a GeoPackage.
"""
import os
import time

import numpy as np

from .features import GSD, MIN_PX, edges_of, feature_names, lch_of, segment_features, to_uint8
from .modes import resolve_mode
from .objects import build_objects, object_features
from .segment import segment

MIN_VALID_PX = 10_000          # a tile with fewer valid pixels is skipped, as in the research


def detect_array(bands, valid, mode, forest, transform=None, threshold=0.5, object_forest=None):
    """The pipeline on one window.

    Parameters
    ----------
    bands : dict role -> 2-D array, values 0-255 (see features.to_uint8)
    valid : bool array (rows, cols)
    mode : Mode
    forest : fitted segment forest of that mode
    transform : affine.Affine, optional -- centroids in map units if given
    threshold : float, absolute probability cut (the tool default is 0.5)
    object_forest : fitted object forest, optional

    Returns
    -------
    dict with seg (labels), prob (per segment), obj_of, n_obj, F (object
    features), centroid (n_obj, 2), p2 (object probability or None),
    obj_raster (int32, 0 = no object, else object id + 1), names, cnt.
    """
    roles = {r: np.asarray(bands[r], np.float32) for r in mode.roles}
    seg = segment(roles, valid, mode)
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


def detect(raster_path, out_path, mode=None, bands=None, threshold=0.5, min_area=0.0,
           tile=2400, overlap=200, stands=None, stand_layer=None, stand_age=10, stand_buffer=-2.0,
           keep_outside=False, object_stage=True, object_threshold=None, prob_raster=None,
           points=False, edge_px=8, model=None, progress=None, quiet=False):
    """Detect dead crowns on a raster and write them to a GeoPackage.

    Parameters
    ----------
    raster_path, out_path : str
        Input orthophoto (any GDAL format) and output GeoPackage.
    mode, bands : see modes.resolve_mode.
    model : str, optional
        Path of an adapted segment forest (adapt.adapt) to use instead of
        the shipped one; it must have been fitted for the same mode.
    progress : callable, optional
        Called as progress(fraction, message) after every tile (and once
        at the start); return False to cancel the run. Meant for GUI
        front ends; the messages are the ones printed when not quiet.
    threshold : float
        Absolute probability cut per adaptel; 0.5 is the calibrated
        default, 0.4-0.6 the useful range.
    min_area : float
        Minimum object area in m2 (0 = none, as calibrated).
    tile, overlap : int
        Tile side and overlap in pixels at 0.25 m.
    stands, stand_layer, stand_age, stand_buffer : stand mask (mask.load_stands).
    keep_outside : bool
        Keep objects outside the stand mask, flagged in_stands = 0.
    object_stage : bool
        Score objects with the object forest (RGBN mode only); the
        probability is written as p_object. With `object_threshold` set,
        objects below it are dropped.
    prob_raster : str, optional
        Also write the per-pixel adaptel probability as a GeoTIFF.
    points : bool
        Also write a centroid layer.
    edge_px : int
        Objects closer than this to nodata or the raster edge are flagged
        (edge_px column), not dropped.
    """
    from . import assets
    from .mask import inside, load_stands, nodata_distance
    from .vectorize import Sink, as_point, points_sink, polygons_of, record

    t_all = time.time()
    src, ds = _open(raster_path, quiet)
    try:
        m, index = resolve_mode(ds.count, mode, bands)
        if model:
            import joblib
            forest = joblib.load(model)
            model_id = os.path.basename(model)
            if not quiet:
                print(f"pygeosnag: adapted forest {model_id}", flush=True)
        else:
            forest = assets.load_forest(m.name, quiet)
            model_id = f"{assets.RELEASE}/{m.name}"
        object_forest = None
        if object_stage:
            if m.name == "rgbn":
                object_forest = assets.load_forest("objects", quiet)
            elif not quiet:
                print("pygeosnag: the object forest exists for the rgbn mode only; skipped", flush=True)
        mask_geom = load_stands(stands, stand_layer, min_age=stand_age, buffer_m=stand_buffer,
                                quiet=quiet) if stands else None
        nodata = ds.nodata if ds.nodata is not None else 0
        crs_wkt = ds.crs.to_wkt() if ds.crs else ""
        if os.path.exists(out_path):
            os.remove(out_path)
        sink = Sink(out_path, crs_wkt)
        psink = points_sink(out_path, crs_wkt) if points else None
        prob_dst = None
        if prob_raster:
            import rasterio
            prof = dict(driver="GTiff", dtype="float32", count=1, width=ds.width, height=ds.height,
                        crs=ds.crs, transform=ds.transform, nodata=-1.0, compress="deflate", tiled=True)
            prob_dst = rasterio.open(prob_raster, "w", **prof)
        H, W = ds.height, ds.width
        tiles = list(_tiles(H, W, tile, overlap))

        def report(frac, msg):
            if not quiet:
                print(msg, flush=True)
            if progress is not None and progress(frac, msg) is False:
                raise RuntimeError("pygeosnag: cancelled")

        report(0.0, f"pygeosnag: {os.path.basename(raster_path)} {W} x {H} px, mode {m.name}, "
                    f"{len(tiles)} tiles, threshold {threshold}")
        n_obj_total = 0
        for k, (r0, c0, h, w, cr0, cr1, cc0, cc1) in enumerate(tiles):
            from rasterio.windows import Window
            t0 = time.time()
            win = Window(c0, r0, w, h)
            arr = ds.read(window=win).astype(np.float32)
            if np.isnan(nodata):
                valid = np.isfinite(arr).all(axis=0)
            else:
                valid = (arr != nodata).all(axis=0) & np.isfinite(arr).all(axis=0)
            if valid.sum() < MIN_VALID_PX:
                report((k + 1) / len(tiles), f"  tile {k + 1}/{len(tiles)} ({r0}_{c0}): nodata, skipped")
                continue
            tf = ds.window_transform(win)
            band_roles = {r: to_uint8(np.where(valid, arr[i], 0.0)) for r, i in index.items()}
            res = detect_array(band_roles, valid, m, forest, tf, threshold, object_forest)
            if prob_dst is not None:
                pr = np.full(valid.shape, -1.0, np.float32)
                lab = res["seg"][valid] - res["seg"][valid].min()
                pr[valid] = res["prob"][lab]
                sl = (slice(cr0 - r0, cr1 - r0), slice(cc0 - c0, cc1 - c0))
                prob_dst.write(pr[sl], 1, window=Window(cc0, cr0, cc1 - cc0, cr1 - cr0))
            n = res["n_obj"]
            if n == 0:
                report((k + 1) / len(tiles), f"  tile {k + 1}/{len(tiles)} ({r0}_{c0}): "
                                             f"{len(res['cnt']):,} adaptels, 0 objects, {time.time() - t0:.0f}s")
                continue
            F, cent, p2 = res["F"], res["centroid"], res["p2"]
            # objects whose centroid lies in the tile core, in pixel space of the tile
            prow, pcol = (~tf) * (cent[:, 0], cent[:, 1])
            pcol, prow = np.asarray(pcol), np.asarray(prow)   # (~tf)*(x, y) -> (col, row)
            grow, gcol = prow + r0, pcol + c0
            keep = (grow >= cr0) & (grow < cr1) & (gcol >= cc0) & (gcol < cc1)
            keep &= F[:, 0] >= min_area
            keep &= np.isfinite(F).all(axis=1)
            in_st = None
            if mask_geom is not None:
                in_st = inside(mask_geom, cent)
                if not keep_outside:
                    keep &= in_st
            if p2 is not None and object_threshold is not None:
                keep &= p2 >= object_threshold
            ids = np.nonzero(keep)[0]
            if not len(ids):
                report((k + 1) / len(tiles), f"  tile {k + 1}/{len(tiles)} ({r0}_{c0}): "
                                             f"{len(res['cnt']):,} adaptels, {n} objects, 0 kept, {time.time() - t0:.0f}s")
                continue
            dist = nodata_distance(valid)
            geoms = polygons_of(res["obj_raster"], tf, ids + 1)
            recs, pts = [], []
            tile_name = f"{r0}_{c0}"
            for i in ids:
                g = geoms.get(int(i) + 1)
                if g is None:
                    continue
                rr = int(np.clip(round(prow[i]), 0, h - 1))
                cc = int(np.clip(round(pcol[i]), 0, w - 1))
                rec = record(g, n_obj_total + len(recs) + 1, F[i], None if p2 is None else p2[i],
                             None if in_st is None else in_st[i], dist[rr, cc], tile_name, m.name, model_id)
                recs.append(rec)
                if psink is not None:
                    pts.append(as_point(rec, cent[i]))
            sink.write(recs)
            if psink is not None and pts:
                psink.writerecords(pts)
            n_obj_total += len(recs)
            report((k + 1) / len(tiles), f"  tile {k + 1}/{len(tiles)} ({tile_name}): {len(res['cnt']):,} adaptels, "
                                         f"{n} objects, {len(recs)} written, {time.time() - t0:.0f}s")
        sink.close()
        if psink is not None:
            psink.close()
        if prob_dst is not None:
            prob_dst.close()
        report(1.0, f"pygeosnag: {n_obj_total} objects -> {out_path} [{time.time() - t_all:.0f}s]")
        return n_obj_total
    finally:
        if ds is not src:
            ds.close()
        src.close()
