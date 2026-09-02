"""Object polygons and the GeoPackage that carries them."""
import numpy as np

SCHEMA = {
    "geometry": "MultiPolygon",
    "properties": {
        "id": "int", "prob_max": "float", "prob_mean": "float", "prob_min": "float",
        "area_m2": "float", "n_segments": "int", "elongation": "float",
        "ring_ndvi": "float", "ring_L": "float", "p_object": "float",
        "in_stands": "int", "edge_px": "float", "tile": "str", "mode": "str", "model": "str",
    },
}


def polygons_of(obj_raster, transform, ids):
    """Geometry (GeoJSON mapping, MultiPolygon) per object id present in `ids`."""
    from rasterio.features import shapes
    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union
    want = set(int(i) for i in ids)
    pieces = {}
    for geom, val in shapes(obj_raster, mask=obj_raster > 0, transform=transform, connectivity=4):
        v = int(val)
        if v in want:
            pieces.setdefault(v, []).append(shape(geom))
    out = {}
    for v, gs in pieces.items():
        g = unary_union(gs) if len(gs) > 1 else gs[0]
        if g.geom_type == "Polygon":
            from shapely.geometry import MultiPolygon
            g = MultiPolygon([g])
        out[v] = mapping(g)
    return out


class Sink:
    """A GeoPackage opened once, written tile by tile."""

    def __init__(self, path, crs_wkt, layer="snags"):
        import fiona
        self.dst = fiona.open(path, "w", driver="GPKG", crs_wkt=crs_wkt, schema=SCHEMA, layer=layer)
        self.n = 0

    def write(self, records):
        if records:
            self.dst.writerecords(records)
            self.n += len(records)

    def close(self):
        self.dst.close()


def record(geom, oid, F, p2, in_stands, edge, tile, mode, model):
    """One feature: F is the object's feature row (see objects.OBJ_BASE)."""
    return {
        "geometry": geom,
        "properties": {
            "id": int(oid), "prob_max": round(float(F[4]), 4), "prob_mean": round(float(F[5]), 4),
            "prob_min": round(float(F[6]), 4), "area_m2": round(float(F[0]), 2),
            "n_segments": int(F[1]), "elongation": round(float(max(F[2], F[3])), 3),
            "ring_ndvi": round(float(F[7]), 4), "ring_L": round(float(F[8]), 2),
            "p_object": None if p2 is None else round(float(p2), 4),
            "in_stands": None if in_stands is None else int(in_stands),
            "edge_px": round(float(edge), 1), "tile": tile, "mode": mode, "model": model,
        },
    }


def points_sink(path, crs_wkt, layer="snag_points"):
    """Optional centroid layer with the same attributes."""
    import fiona
    schema = dict(SCHEMA)
    schema["geometry"] = "Point"
    return fiona.open(path, "w", driver="GPKG", crs_wkt=crs_wkt, schema=schema, layer=layer)


def as_point(rec, xy):
    r = dict(rec)
    r["geometry"] = {"type": "Point", "coordinates": (float(xy[0]), float(xy[1]))}
    return r


def is_finite_row(F):
    return bool(np.all(np.isfinite(F)))
