"""Grow dead-tree points into crowns -- pygeoadaptels' seeded growing with
crown defaults.

`grow_seeds` (inverse OBIA: every seed grows into the region that looks
like the pixel it sits on, with a spectral tolerance and a radius cap)
lives in pygeoadaptels and is not copied here; this is the recipe wrapped
around it. The recipe was worked out on a spruce plot with bleached snags:
grow on CIELAB, weight a* twice and a half (the red-green axis separates
grey-white crowns from green canopy), stop at a Delta-E of 15, never
further than 20 px (5 m at 0.25 m), fill the holes a bright spot or a
shadow leaves inside a crown.
"""
import os
import tempfile

import numpy as np

from .features import to_uint8
from .modes import resolve_mode

RECIPE = dict(max_cost=15.0, band_weights=(0.5, 2.5, 1.0), max_radius=20, fill_holes=True)


def lab_raster(raster_path, out_path, mode=None, bands=None, quiet=False):
    """CIELAB of the mode's RGB-like trio (RGB, or NIR-R-G in the CIR mode) as a 3-band GeoTIFF."""
    import pygeopalette as gp
    import rasterio
    with rasterio.open(raster_path) as src:
        m, index = resolve_mode(src.count, mode, bands)
        arr = src.read().astype(np.float32)
        nodata = src.nodata if src.nodata is not None else 0
        valid = (arr != nodata).all(axis=0) & np.isfinite(arr).all(axis=0)
        trio = [np.clip(to_uint8(np.where(valid, arr[index[r]], 0.0)), 0, 255).astype(np.uint8) for r in m.lch_trio]
        comps, names = gp.convertbands(trio[0], trio[1], trio[2], "lab")
        lab = np.stack([np.asarray(c, np.float32) for c in comps])
        lab[:, ~valid] = np.nan
        prof = src.profile
        prof.update(driver="GTiff", count=3, dtype="float32", nodata=np.nan, compress="deflate")
        with rasterio.open(out_path, "w", **prof) as dst:
            dst.write(lab)
            dst.descriptions = tuple(names)
    if not quiet:
        print(f"pygeosnag: CIELAB from {os.path.basename(raster_path)} ({m.name}) -> {out_path}", flush=True)
    return out_path


def grow_crowns(raster_path, points_path, out_polygons, mode=None, bands=None, labels_out=None,
                points_layer=None, quiet=False, **recipe):
    """Grow a point layer of dead trees into crown polygons.

    Parameters
    ----------
    raster_path : str
        The orthophoto the points were detected on.
    points_path : str
        Point layer (any OGR format; ``path|layername=x`` accepted).
    out_polygons : str
        Output crown polygons (.gpkg).
    mode, bands : as in detect -- decide which bands make the CIELAB.
    labels_out : str, optional
        Also write the label raster (int32, -1 unassigned).
    recipe : max_cost, band_weights, max_radius, fill_holes, compactness,
        seed_window -- overrides of RECIPE, passed to grow_seeds.
    """
    from pygeoadaptels.grow import grow_seeds_from_files
    if "|" in str(points_path):
        points_path, _, rest = str(points_path).partition("|")
        for part in rest.split("|"):
            if part.startswith("layername="):
                points_layer = part[len("layername="):]
    kw = dict(RECIPE)
    kw.update({k: v for k, v in recipe.items() if v is not None})
    kw["band_weights"] = list(kw["band_weights"])
    td = tempfile.mkdtemp(prefix="geosnag_lab_")
    lab = os.path.join(td, "lab.tif")
    try:
        lab_raster(raster_path, lab, mode, bands, quiet)
        if os.path.exists(out_polygons):
            os.remove(out_polygons)
        result = grow_seeds_from_files(lab, points_path, output_file=labels_out, polygons=out_polygons,
                                       points_layer=points_layer, quiet=quiet, **kw)
    finally:
        try:
            os.remove(lab)
            os.rmdir(td)
        except OSError:
            pass
    if not quiet:
        print(f"pygeosnag: crowns -> {out_polygons}", flush=True)
    return result
