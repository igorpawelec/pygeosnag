"""
pygeosnag -- standing dead tree (snag) detection on aerial orthophotos.

A raster goes in, a GeoPackage of dead-crown polygons with a confidence
score comes out. Nothing else is required: no seeds, no tree tops, no
canopy height model. Under the hood:

1. adaptels (scale-adaptive superpixels, pygeoadaptels) at a granularity
   chosen for 0.25 m orthophotos, on whichever bands the raster has;
2. twenty features per adaptel -- vegetation indices, CIELCh lightness,
   chroma and hue, each with its mean, spread and contrast to a 25 m
   neighbourhood, plus size and elongation;
3. a random forest trained on seven Polish forest sites, one forest per
   band mode (RGB+NIR, CIR, RGB);
4. an absolute probability threshold, merging of adjacent detections into
   objects, an optional stand mask and an optional second forest on the
   object itself.

Usage::

    from pygeosnag import detect
    detect("ortho.tif", "snags.gpkg")                 # 4 bands -> rgbn
    detect("cir.tif", "snags.gpkg", mode="cir")       # 3 bands NIR, R, G

    geosnag detect ortho.tif -o snags.gpkg --stands wydzielenia.gpkg

The models are downloaded on first use from the package's GitHub release
and cached locally; set PYGEOSNAG_ASSETS to point at a directory that
already holds them.
"""

try:
    from importlib.metadata import version as _version
    __version__ = _version("pygeosnag")
except Exception:
    __version__ = "0.1.0"

__author__ = "Igor Pawelec"

from .modes import MODES, resolve_mode  # noqa: E402
from .features import FEATURE_NAMES, feature_names  # noqa: E402

_LAZY = {
    "detect": ".detect",
    "detect_array": ".detect",
    "adapt": ".adapt",
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
           "detect", "detect_array", "adapt", "segment_features", "load_forest", "__version__"]
