"""The point layer that is the product: one point per dead tree."""

SCHEMA = {
    "geometry": "Point",
    "properties": {
        "id": "int", "p": "float", "p_mean": "float", "p_object": "float",
        "area_m2": "float", "n_adaptels": "int", "in_stands": "int", "height_m": "float",
        "edge_px": "float", "tile": "str", "mode": "str", "model": "str",
    },
}


class PointSink:
    """A GeoPackage opened once, written tile by tile."""

    def __init__(self, path, crs_wkt, layer="dead_trees"):
        import fiona
        self.dst = fiona.open(path, "w", driver="GPKG", crs_wkt=crs_wkt, schema=SCHEMA, layer=layer)
        self.n = 0

    def write(self, records):
        if records:
            self.dst.writerecords(records)
            self.n += len(records)

    def close(self):
        self.dst.close()


def point_record(xy, oid, F, p2, in_stands, edge, tile, mode, model, height=None):
    """One dead tree: F is the object's feature row (see objects.OBJ_BASE)."""
    return {
        "geometry": {"type": "Point", "coordinates": (float(xy[0]), float(xy[1]))},
        "properties": {
            "id": int(oid), "p": round(float(F[4]), 4), "p_mean": round(float(F[5]), 4),
            "p_object": None if p2 is None else round(float(p2), 4),
            "area_m2": round(float(F[0]), 2), "n_adaptels": int(F[1]),
            "in_stands": None if in_stands is None else int(in_stands),
            "height_m": None if height is None else round(float(height), 2),
            "edge_px": None if edge is None else round(float(edge), 1),
            "tile": tile, "mode": mode, "model": model,
        },
    }
