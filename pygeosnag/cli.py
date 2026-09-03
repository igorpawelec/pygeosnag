"""geosnag -- command line front end.

    geosnag detect ortho.tif -o trees.gpkg [--mode rgbn|cir|rgb] [--bands red,green,blue,nir]
                   [--threshold 0.5] [--stands stands.gpkg] [--prob-raster p.tif] [--quiet]
    geosnag grow   ortho.tif trees.gpkg -o crowns.gpkg [--mode ...] [--max-cost 15] [--max-radius 20]
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
    n = detect(a.raster, a.output, mode=a.mode, bands=bands, threshold=a.threshold, suppress_m=a.suppress,
               min_area=a.min_area, stands=a.stands, stand_layer=a.stand_layer, stand_age=a.stand_age,
               stand_buffer=a.stand_buffer, keep_outside=a.keep_outside,
               chm=a.chm, dtm=a.dtm, dsm=a.dsm, min_height=a.min_height, keep_low=a.keep_low,
               object_stage=not a.no_object_stage,
               object_threshold=a.object_threshold, prob_raster=a.prob_raster, edge_px=a.edge_px,
               tile=a.tile, overlap=a.overlap, model=a.model, adaptel_threshold=a.adaptel_threshold, quiet=a.quiet)
    return 0 if n >= 0 else 1


def _grow(a):
    from .grow import grow_crowns
    bands = tuple(b.strip() for b in a.bands.split(",")) if a.bands else None
    weights = tuple(float(x) for x in a.band_weights.split(",")) if a.band_weights else None
    grow_crowns(a.raster, a.points, a.output, mode=a.mode, bands=bands, labels_out=a.labels,
                max_cost=a.max_cost, band_weights=weights, max_radius=a.max_radius,
                fill_holes=not a.no_fill_holes, quiet=a.quiet)
    return 0


def _info(a):
    from . import assets
    print(f"pygeosnag {__version__}")
    print(f"models: {assets.assets_dir()} (release {assets.RELEASE})")
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

    d = sub.add_parser("detect", help="one point per dead tree")
    d.add_argument("raster")
    d.add_argument("-o", "--output", required=True, help="output GeoPackage (layer dead_trees)")
    d.add_argument("--mode", choices=sorted(MODES), default=None, help="band mode (default: rgbn for 4 bands, rgb for 3)")
    d.add_argument("--bands", default=None, help="role of each raster band in order, e.g. nir,red,green,blue")
    d.add_argument("--threshold", type=float, default=0.5, help="probability cut per adaptel (default 0.5)")
    d.add_argument("--stands", default=None, help="stand polygons for the forest mask")
    d.add_argument("--stand-layer", default=None)
    d.add_argument("--stand-age", type=float, default=10)
    d.add_argument("--stand-buffer", type=float, default=-2.0)
    d.add_argument("--keep-outside", action="store_true")
    d.add_argument("--chm", default=None, help="canopy height model: points below --min-height are dropped")
    d.add_argument("--dtm", default=None, help="terrain model, with --dsm an alternative to --chm")
    d.add_argument("--dsm", default=None, help="surface model, with --dtm an alternative to --chm")
    d.add_argument("--min-height", type=float, default=5.0, help="height gate in metres (default 5)")
    d.add_argument("--keep-low", action="store_true", help="keep points below the gate, with height_m written")
    d.add_argument("--prob-raster", default=None, help="also write the per-pixel probability GeoTIFF")
    d.add_argument("--suppress", type=float, default=3.0, help="drop the weaker of two points closer than this, m")
    d.add_argument("--min-area", type=float, default=0.0)
    d.add_argument("--no-object-stage", action="store_true")
    d.add_argument("--object-threshold", type=float, default=None)
    d.add_argument("--edge-px", type=int, default=8)
    d.add_argument("--tile", type=int, default=2400)
    d.add_argument("--overlap", type=int, default=200)
    d.add_argument("--model", default=None, help="a segment forest .joblib instead of the shipped one")
    d.add_argument("--adaptel-threshold", type=float, default=None)
    d.add_argument("--quiet", action="store_true")
    d.set_defaults(func=_detect)

    g = sub.add_parser("grow", help="grow dead-tree points into crowns (pygeoadaptels grow_seeds, crown recipe)")
    g.add_argument("raster")
    g.add_argument("points", help="point layer, e.g. the dead_trees layer of detect")
    g.add_argument("-o", "--output", required=True, help="output crown polygons (.gpkg)")
    g.add_argument("--mode", choices=sorted(MODES), default=None)
    g.add_argument("--bands", default=None)
    g.add_argument("--labels", default=None, help="also write the label raster")
    g.add_argument("--max-cost", type=float, default=None, help="Delta-E tolerance (default 15)")
    g.add_argument("--band-weights", default=None, help="L,a,b weights (default 0.5,2.5,1.0)")
    g.add_argument("--max-radius", type=float, default=None, help="pixels from the seed (default 20)")
    g.add_argument("--no-fill-holes", action="store_true")
    g.add_argument("--quiet", action="store_true")
    g.set_defaults(func=_grow)

    i = sub.add_parser("info", help="modes, model location and manifest")
    i.set_defaults(func=_info)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
