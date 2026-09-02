"""
pygeosnag -- standing dead trees on aerial orthophotos, as points.

A raster goes in, one point per dead tree comes out, with a confidence.
The points are seeds: `grow_crowns` grows them into crown polygons with
pygeoadaptels' seeded region growing and a crown recipe. Under the hood
of `detect`:

1. adaptels (scale-adaptive superpixels, pygeoadaptels) at a granularity
   chosen for 0.25 m orthophotos, on whichever bands the raster has;
2. twenty features per adaptel -- vegetation indices, CIELCh lightness,
   chroma and hue, each with its mean, spread and contrast to a 25 m
   neighbourhood, plus size and elongation;
3. a random forest trained on seven Polish forest sites, one per band
   mode (RGB+NIR, CIR, RGB);
4. an absolute probability threshold, merging of adjacent detections into
   one object, the object's centroid as the point, the weaker of two
   points closer than a crown radius dropped, an optional stand mask.

Usage::

    from pygeosnag import detect, grow_crowns
    detect("ortho.tif", "trees.gpkg")                   # 4 bands -> rgbn
    detect("cir.tif", "trees.gpkg", mode="cir")         # 3 bands NIR, R, G
    grow_crowns("ortho.tif", "trees.gpkg", "crowns.gpkg")

    geosnag detect ortho.tif -o trees.gpkg --stands wydzielenia.gpkg
    geosnag grow ortho.tif trees.gpkg -o crowns.gpkg

The models are downloaded on first use from the package's GitHub release
and cached in ~/.cache/pygeosnag/; set PYGEOSNAG_ASSETS to a directory
that already holds them.
"""

try:
    from importlib.metadata import version as _version
    __version__ = _version("pygeosnag")
except Exception:
    __version__ = "0.2.0"

__author__ = "Igor Pawelec"

from .modes import MODES, resolve_mode  # noqa: E402
from .features import FEATURE_NAMES, feature_names  # noqa: E402

_LAZY = {
    "detect": ".detect",
    "detect_array": ".detect",
    "grow_crowns": ".grow",
    "lab_raster": ".grow",
    "segment_features": ".features",
    "load_forest": ".assets",
}


def __getattr__(name):
    if name in _LAZY:
        import importlib
        mod = importlib.import_module(_LAZY[name], __name__)
        obj = getattr(mod, name)
        globals()[name] = obj
        return obj
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["MODES", "resolve_mode", "FEATURE_NAMES", "feature_names",
           "detect", "detect_array", "grow_crowns", "lab_raster", "segment_features", "load_forest",
           "__version__"]
