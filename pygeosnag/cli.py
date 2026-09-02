"""geosnag -- command line front end.

    geosnag detect ortho.tif -o snags.gpkg [--mode rgbn|cir|rgb] [--bands red,green,blue,nir]
                   [--threshold 0.5] [--min-area 0] [--stands stands.gpkg --stand-age 10 --stand-buffer -2]
                   [--keep-outside] [--no-object-stage] [--object-threshold 0.4]
                   [--prob-raster prob.tif] [--points] [--tile 2400] [--overlap 200] [--quiet]
    geosnag info

Console output is plain ASCII on purpose: Windows consoles in code page
1250 choke on anything else.
"""
import argparse
import sys

from . import __version__
from .modes import MODES


def _detect(a):
    from .detect import detect
    bands = tuple(b.strip() for b in a.bands.split(",")) if a.bands else None
    n = detect(a.raster, a.output, mode=a.mode, bands=bands, threshold=a.threshold, min_area=a.min_area,
               tile=a.tile, overlap=a.overlap, stands=a.stands, stand_layer=a.stand_layer,
               stand_age=a.stand_age, stand_buffer=a.stand_buffer, keep_outside=a.keep_outside,
               object_stage=not a.no_object_stage, object_threshold=a.object_threshold,
               prob_raster=a.prob_raster, points=a.points, edge_px=a.edge_px, quiet=a.quiet)
    return 0 if n >= 0 else 1


def _info(a):
    from . import assets
    print(f"pygeosnag {__version__}")
    print(f"assets: {assets.assets_dir()} (release {assets.RELEASE})")
    for k, m in MODES.items():
        print(f"  mode {k:<5} bands {', '.join(m.roles):<22} adaptels t{m.threshold:g}  {m.description}")
    try:
        man = assets.manifest(quiet=True)
        print(f"manifest: created {man.get('created')}, sklearn {man.get('sklearn')}, "
              f"operating point p >= {man['operating_point']['threshold']}")
        for key, f in man["files"].items():
            print(f"  {key:<16} {f['kind']:<32} rows {f.get('rows', 0):,}")
    except Exception as e:                      # noqa: BLE001 -- info must never crash
        print(f"manifest: not available ({e})")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="geosnag", description="Standing dead tree detection on aerial orthophotos.")
    p.add_argument("--version", action="version", version=f"geosnag {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect", help="detect dead crowns on a raster")
    d.add_argument("raster")
    d.add_argument("-o", "--output", required=True, help="output GeoPackage")
    d.add_argument("--mode", choices=sorted(MODES), default=None, help="band mode (default: rgbn for 4 bands, rgb for 3)")
    d.add_argument("--bands", default=None, help="role of each raster band in order, e.g. nir,red,green,blue")
    d.add_argument("--threshold", type=float, default=0.5, help="probability cut per adaptel (default 0.5)")
    d.add_argument("--min-area", type=float, default=0.0, help="minimum object area, m2 (default 0)")
    d.add_argument("--stands", default=None, help="stand polygons (GeoPackage, Shapefile, ...) for the forest mask")
    d.add_argument("--stand-layer", default=None)
    d.add_argument("--stand-age", type=float, default=10, help="minimum stand age in the mask (default 10)")
    d.add_argument("--stand-buffer", type=float, default=-2.0, help="inward buffer of the mask, m (default -2)")
    d.add_argument("--keep-outside", action="store_true", help="keep objects outside the mask, flagged")
    d.add_argument("--no-object-stage", action="store_true", help="skip the object forest")
    d.add_argument("--object-threshold", type=float, default=None, help="drop objects below this object probability")
    d.add_argument("--prob-raster", default=None, help="also write the per-pixel probability GeoTIFF")
    d.add_argument("--points", action="store_true", help="also write a centroid layer")
    d.add_argument("--edge-px", type=int, default=8)
    d.add_argument("--tile", type=int, default=2400)
    d.add_argument("--overlap", type=int, default=200)
    d.add_argument("--quiet", action="store_true")
    d.set_defaults(func=_detect)
    i = sub.add_parser("info", help="modes, asset location and manifest")
    i.set_defaults(func=_info)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
