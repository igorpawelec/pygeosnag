"""Grow dead-tree points into crowns -- pygeoadaptels' seeded growing with
crown defaults, tile by tile around the points.

`grow_seeds` (inverse OBIA: every seed grows into the region that looks
like the pixel it sits on, with a spectral tolerance and a radius cap)
lives in pygeoadaptels and is not copied here; this is the recipe wrapped
around it. The recipe was worked out on a spruce plot with bleached snags:
grow on CIELAB, weight a* twice and a half (the red-green axis separates
grey-white crowns from green canopy), stop at a Delta-E of 15, never
further than 20 px (5 m at 0.25 m), fill the holes a bright spot or a
shadow leaves inside a crown.

Since 0.3.4 the raster is never read whole. A crown reaches at most
`max_radius` from its point, so the growing runs on windows around the
points: the raster is cut into tiles (row bands for a striped GeoTIFF,
squares for a tiled one), every tile that holds a point is read with a
halo of twice the radius, converted to CIELAB in memory, grown with every
point inside the window as a competitor, and only the crowns of the points
in the tile core are kept. No temporary file, memory bounded by the
window: on a 796-megapixel CIR orthophoto the first version read 9.5 GB,
converted it whole and died writing the CIELAB copy to the temp drive.
The halo of two radii keeps the competition between neighbouring crowns
as on the whole raster; a growth path that leaves the window and comes
back could in theory change a pixel at a tile edge -- measured on a
2400 px window cut into 600 px tiles against the whole window, see the
test and the changelog.
"""
import os
import time

import numpy as np

from .features import to_uint8
from .modes import resolve_mode

RECIPE = dict(max_cost=15.0, band_weights=(0.5, 2.5, 1.0), max_radius=20, fill_holes=True)
TARGET_WINDOW_PX = 40_000_000       # a full-width row band is kept under this many pixels

# Feature spaces the growing can run on, with the tolerance each was benchmarked at
# (SDT_research2026/80_grow_bench, 2026-09-08: 8 verified sites, 1113 crowns, seeds = the
# reference tops, competitors = the detector's points; tolerance chosen on Gizycko):
#   lab_w   CIELAB of the RGB-like trio, a* weighted 2.5 -- the shipped recipe: IoU median 0.53
#   lab     CIELAB unweighted, 30:                                              0.55
#   ndvi_L  100 * NDVI and CIELAB L, 45 (needs a NIR band):                    0.62
#   raw     the three bands as digital numbers, 70:                             0.43
SPACES = {
    "lab_w": dict(max_cost=15.0, band_weights=(0.5, 2.5, 1.0)),
    "lab": dict(max_cost=30.0, band_weights=None),
    "ndvi_L": dict(max_cost=45.0, band_weights=None),
    "raw": dict(max_cost=70.0, band_weights=None),
}


def lab_raster(raster_path, out_path, mode=None, bands=None, quiet=False):
    """CIELAB of the mode's RGB-like trio (RGB, or NIR-R-G in the CIR mode) as a 3-band GeoTIFF.

    Reads the raster whole; kept for small rasters and for inspection. `grow_crowns`
    no longer needs it."""
    import rasterio
    with rasterio.open(raster_path) as src:
        m, index = resolve_mode(src.count, mode, bands)
        arr = src.read().astype(np.float32)
        nodata = src.nodata if src.nodata is not None else 0
        lab, valid = _lab_window(arr, nodata, index, m.lch_trio)
        lab[:, ~valid] = np.nan
        prof = src.profile
        prof.update(driver="GTiff", count=3, dtype="float32", nodata=np.nan, compress="deflate",
                    tiled=True, BIGTIFF="IF_SAFER")
        with rasterio.open(out_path, "w", **prof) as dst:
            dst.write(lab)
            dst.descriptions = ("L", "a", "b")
    if not quiet:
        print(f"pygeosnag: CIELAB from {os.path.basename(raster_path)} ({m.name}) -> {out_path}", flush=True)
    return out_path


def _lab_window(arr, nodata, index, lch_trio, space="lab_w"):
    """Feature stack (bands, h, w) float32 of one window of raw bands, and the valid mask.

    lab_w / lab: CIELAB of the mode's RGB-like trio; ndvi_L: 100 * NDVI (needs the nir and
    red roles) and L; raw: the trio's digital numbers."""
    import pygeopalette as gp
    if nodata is not None and np.isnan(nodata):
        valid = np.isfinite(arr).all(axis=0)
    else:
        valid = (arr != nodata).all(axis=0) & np.isfinite(arr).all(axis=0)
    trio = [np.clip(to_uint8(np.where(valid, arr[index[r]], 0.0)), 0, 255).astype(np.uint8) for r in lch_trio]
    if space == "raw":
        return np.stack([t.astype(np.float32) for t in trio]), valid
    comps, _ = gp.convertbands(trio[0], trio[1], trio[2], "lab")
    lab = np.stack([np.asarray(c, np.float32) for c in comps])
    if space in ("lab_w", "lab"):
        return lab, valid
    if space == "ndvi_L":
        if "nir" not in index or "red" not in index:
            raise ValueError("space ndvi_L needs a NIR band (mode rgbn or cir); this raster has none")
        nir = np.clip(to_uint8(np.where(valid, arr[index["nir"]], 0.0)), 0, 255).astype(np.float32)
        red = np.clip(to_uint8(np.where(valid, arr[index["red"]], 0.0)), 0, 255).astype(np.float32)
        ndvi = (nir - red) / np.maximum(nir + red, 1e-6)
        return np.stack([100.0 * ndvi, lab[0]]), valid
    raise ValueError(f"unknown space {space!r}; choose from {sorted(SPACES)}")


def _tiles(height, width, striped, tile):
    """Tile cores (r0, r1, c0, c1). Full-width row bands for a striped raster (a
    column window would read every strip anyway), squares for a tiled one."""
    if striped:
        rows = int(max(256, min(tile, TARGET_WINDOW_PX // max(width, 1))))
        return [(r0, min(r0 + rows, height), 0, width) for r0 in range(0, height, rows)]
    out = []
    for r0 in range(0, height, tile):
        for c0 in range(0, width, tile):
            out.append((r0, min(r0 + tile, height), c0, min(c0 + tile, width)))
    return out


def _grow_tile(raster_path, core, halo, seeds_rc, index, lch_trio, recipe, space="lab_w"):
    """Grow one tile: read core + halo, CIELAB, grow_seeds with every point in the
    window, keep the crowns of the core's points. Returns (core labels with GLOBAL
    point ids, -1 unassigned; core transform; pixel counts per id; points in core)
    or None when the window holds no usable point."""
    import rasterio
    from rasterio.windows import Window
    from pygeoadaptels.grow import grow_seeds
    r0, r1, c0, c1 = core
    with rasterio.open(raster_path) as src:
        H, W = src.height, src.width
        wr0, wr1 = max(0, r0 - halo), min(H, r1 + halo)
        wc0, wc1 = max(0, c0 - halo), min(W, c1 + halo)
        arr = src.read(window=Window(wc0, wr0, wc1 - wc0, wr1 - wr0)).astype(np.float32)
        nodata = src.nodata if src.nodata is not None else 0.0
        core_transform = src.window_transform(Window(c0, r0, c1 - c0, r1 - r0))
    inside = ((seeds_rc[:, 0] >= wr0) & (seeds_rc[:, 0] < wr1) & (seeds_rc[:, 1] >= wc0) & (seeds_rc[:, 1] < wc1))
    gid = np.flatnonzero(inside)
    lab, valid = _lab_window(arr, nodata, index, lch_trio, space)
    del arr
    local = np.column_stack([seeds_rc[gid, 0] - wr0, seeds_rc[gid, 1] - wc0]).astype(np.int64)
    ok = valid[local[:, 0], local[:, 1]]          # a point on nodata grows nothing
    gid, local = gid[ok], local[ok]
    if len(gid) == 0:
        return None
    labels = grow_seeds(lab, local, mask=(~valid).astype(np.uint8), quiet=True, **recipe)
    is_core = ((seeds_rc[gid, 0] >= r0) & (seeds_rc[gid, 0] < r1) & (seeds_rc[gid, 1] >= c0) & (seeds_rc[gid, 1] < c1))
    to_global = np.where(is_core, gid, -1).astype(np.int32)
    lab_global = np.where(labels >= 0, to_global[np.clip(labels, 0, None)], -1).astype(np.int32)
    core_labels = np.ascontiguousarray(lab_global[r0 - wr0:r1 - wr0, c0 - wc0:c1 - wc0])
    assigned = core_labels[core_labels >= 0]
    counts = {}
    if assigned.size:
        ids, n = np.unique(assigned, return_counts=True)
        counts = dict(zip(ids.tolist(), n.tolist()))
    return core_labels, core_transform, counts, int(is_core.sum())


def _grow_tile_star(a):
    return _grow_tile(*a)


def grow_crowns(raster_path, points_path, out_polygons, mode=None, bands=None, labels_out=None,
                points_layer=None, tile=2048, halo=None, workers=1, progress=None, quiet=False, space="lab_w",
                **recipe):
    """Grow a point layer of dead trees into crown polygons, tile by tile.

    Parameters
    ----------
    raster_path : str
        The orthophoto the points were detected on (read in windows, never whole).
    points_path : str
        Point layer (any OGR format; ``path|layername=x`` accepted).
    out_polygons : str
        Output crowns (.gpkg, layer ``crowns``): one MultiPolygon per point that
        grew, ``adaptel_id`` = the point's index in the layer (0-based),
        ``area_m2``, ``perimeter``, ``n_parts``.
    mode, bands : as in detect -- decide which bands make the CIELAB.
    labels_out : str, optional
        Also write the label raster (int32, -1 unassigned, tiled GeoTIFF).
    tile : int
        Core tile side in pixels; on a striped GeoTIFF the row-band height,
        capped so a band stays under 40 megapixels.
    halo : int, optional
        Pixels read around the core; default twice ``max_radius``.
    workers : int
        Tiles grown in parallel processes. Keep 1 inside QGIS (its Python has
        no interpreter to spawn).
    progress : callable(fraction, message) -> bool, optional
        Called after every tile; False cancels (RuntimeError "cancelled").
    space : "lab_w" | "lab" | "ndvi_L" | "raw"
        Feature space of the growing (SPACES): the shipped recipe is CIELAB with a*
        weighted 2.5; "ndvi_L" (100 * NDVI and L, tolerance 45) grew the best crowns
        on the 8-site benchmark (IoU median 0.62 against 0.53) and needs a NIR band.
        Each space carries its own default tolerance and band weights; ``max_cost``
        and ``band_weights`` in ``recipe`` override them.
    recipe : max_cost, band_weights, max_radius, fill_holes, compactness,
        seed_window -- overrides of RECIPE, passed to grow_seeds.

    Returns
    -------
    int : number of crowns written.
    """
    import rasterio
    from rasterio.features import shapes
    from rasterio.windows import Window
    from pygeoadaptels.grow import _point_to_pixel, _read_points
    if "|" in str(points_path):
        points_path, _, rest = str(points_path).partition("|")
        for part in rest.split("|"):
            if part.startswith("layername="):
                points_layer = part[len("layername="):]
    if space not in SPACES:
        raise ValueError(f"unknown space {space!r}; choose from {sorted(SPACES)}")
    kw = dict(RECIPE)
    kw.update(SPACES[space])
    kw.update({k: v for k, v in recipe.items() if v is not None})
    kw["band_weights"] = list(kw["band_weights"]) if kw.get("band_weights") is not None else None
    if halo is None:
        halo = int(np.ceil(2 * (kw.get("max_radius") or 20)))
    halo = max(int(halo), 8)
    t_all = time.time()

    def report(frac, msg):
        if not quiet:
            print(msg, flush=True)
        if progress is not None and progress(frac, msg) is False:
            raise RuntimeError("pygeosnag: cancelled")

    with rasterio.open(raster_path) as src:
        m, index = resolve_mode(src.count, mode, bands)
        H, W = src.height, src.width
        tr = src.transform
        crs = src.crs
        striped = (not src.is_tiled) or src.block_shapes[0][1] >= W
        xy = _read_points(points_path, points_layer, crs, quiet)
        px_area = abs(tr.a * tr.e)
        prof = src.profile.copy()
    seeds_rc = np.array([_point_to_pixel(x, y, tr.c, tr.f, tr.a, -tr.e) for x, y in xy], dtype=np.int64)
    on_raster = (seeds_rc[:, 0] >= 0) & (seeds_rc[:, 0] < H) & (seeds_rc[:, 1] >= 0) & (seeds_rc[:, 1] < W)
    rr, cc = seeds_rc[on_raster, 0], seeds_rc[on_raster, 1]
    cores = _tiles(H, W, striped, tile)
    with_seeds = [c for c in cores if ((rr >= c[0]) & (rr < c[1]) & (cc >= c[2]) & (cc < c[3])).any()]
    report(0.0, f"pygeosnag: {os.path.basename(raster_path)} {W} x {H} px, mode {m.name}, {len(xy)} points "
                f"({int((~on_raster).sum())} off the raster), {len(with_seeds)} of {len(cores)} tiles hold points, "
                f"halo {halo} px, space {space}, recipe {kw}")

    dst_labels = None
    if labels_out:
        lp = prof.copy()
        lp.update(driver="GTiff", count=1, dtype="int32", nodata=-1, compress="deflate", tiled=True,
                  blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
        lp.pop("photometric", None)
        dst_labels = rasterio.open(labels_out, "w", **lp)
        empty = set(cores) - set(with_seeds)
        for (r0, r1, c0, c1) in empty:
            dst_labels.write(np.full((r1 - r0, c1 - c0), -1, np.int32), 1, window=Window(c0, r0, c1 - c0, r1 - r0))

    n_pts = len(xy)
    counts = np.zeros(max(n_pts, 1), dtype=np.int64)
    parts = {}                                   # adaptel_id -> polygon geometries (GeoJSON dicts)
    args = [(raster_path, core, halo, seeds_rc, index, m.lch_trio, kw, space) for core in with_seeds]

    def consume(k, core, res):
        r0, r1, c0, c1 = core
        if res is None:
            if dst_labels is not None:
                dst_labels.write(np.full((r1 - r0, c1 - c0), -1, np.int32), 1, window=Window(c0, r0, c1 - c0, r1 - r0))
            report((k + 1) / max(1, len(with_seeds)), f"  tile {k + 1}/{len(with_seeds)} ({r0}_{c0}): no usable point")
            return
        core_labels, core_transform, cnt, n_core = res
        for gid_, n in cnt.items():
            counts[gid_] += n
        if dst_labels is not None:
            dst_labels.write(core_labels, 1, window=Window(c0, r0, c1 - c0, r1 - r0))
        mask = core_labels >= 0
        if mask.any():
            for geom, value in shapes(core_labels, mask=mask, transform=core_transform, connectivity=8):
                parts.setdefault(int(value), []).append(geom)
        report((k + 1) / max(1, len(with_seeds)),
               f"  tile {k + 1}/{len(with_seeds)} ({r0}_{c0}): {n_core} points, {int(mask.sum()):,} px assigned")

    try:
        if workers and int(workers) > 1 and len(args) > 1:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=int(workers)) as ex:
                for k, (core, res) in enumerate(zip(with_seeds, ex.map(_grow_tile_star, args))):
                    consume(k, core, res)
        else:
            for k, (core, a) in enumerate(zip(with_seeds, args)):
                consume(k, core, _grow_tile(*a))
    finally:
        if dst_labels is not None:
            dst_labels.close()

    import fiona
    from shapely.geometry import MultiPolygon, mapping, shape
    from shapely.ops import unary_union
    if os.path.exists(out_polygons):
        os.remove(out_polygons)
    schema = {"geometry": "MultiPolygon",
              "properties": {"adaptel_id": "int", "area_m2": "float", "perimeter": "float", "n_parts": "int"}}
    n_written = 0
    with fiona.open(out_polygons, "w", driver="GPKG", crs_wkt=crs.to_wkt() if crs else None, schema=schema,
                    layer="crowns") as dst:
        batch = []
        for gid_ in sorted(parts):
            geoms = [shape(g) for g in parts[gid_]]
            geom = unary_union(geoms) if len(geoms) > 1 else geoms[0]
            if geom.geom_type == "Polygon":
                geom = MultiPolygon([geom])
            area = float(counts[gid_] * px_area)
            batch.append({"geometry": mapping(geom),
                          "properties": {"adaptel_id": int(gid_), "area_m2": round(area, 2),
                                         "perimeter": round(float(2.0 * np.sqrt(np.pi * area)), 2),
                                         "n_parts": len(geom.geoms)}})
            if len(batch) >= 2000:
                dst.writerecords(batch)
                n_written += len(batch)
                batch = []
        if batch:
            dst.writerecords(batch)
            n_written += len(batch)
    if not quiet:
        print(f"pygeosnag: {n_written} crowns from {n_pts} points -> {out_polygons} [{time.time() - t_all:.0f}s]",
              flush=True)
    return n_written
