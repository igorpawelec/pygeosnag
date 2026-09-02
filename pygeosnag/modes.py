"""Band modes: which bands the raster has decides the segmentation, the
feature set and the forest.

The detector was developed on 4-band orthophotos (R, G, B, NIR). An RGB
orthophoto has no NIR and a CIR one has no blue, so each mode gets its
own segmentation on the bands it has, its own feature set (no NDVI
without NIR, no NDBR without blue) and its own forest, trained from the
same sites by dropping bands.

The adaptel threshold is a granularity, not a number: the Minkowski
distance sums over bands, so t60 on three bands would grow coarser
adaptels than t60 on four. The three-band thresholds were matched to the
RGBN t60 segment count on the same windows (RGB t40 = 1.04x, CIR t50 =
1.08x; RGB t60 would have been 0.60x).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Mode:
    name: str
    roles: tuple          # bands, in the order the segmentation sees them
    threshold: float      # adaptel threshold matched to RGBN t60
    indices: tuple        # spectral indices available in this mode
    lch_trio: tuple       # roles pushed through the RGB -> CIELCh transform
    description: str


MODES = {
    "rgbn": Mode("rgbn", ("red", "green", "blue", "nir"), 60.0, ("NDVI", "NDGR", "NDBR"),
                 ("red", "green", "blue"), "R, G, B, NIR -- the reference mode, 20 features"),
    "cir": Mode("cir", ("nir", "red", "green"), 50.0, ("NDVI", "NDGR"),
                ("nir", "red", "green"), "NIR, R, G (colour infrared) -- no blue, 17 features"),
    "rgb": Mode("rgb", ("red", "green", "blue"), 40.0, ("NDGR", "NDBR"),
                ("red", "green", "blue"), "R, G, B -- no NIR, 17 features"),
}

DEFAULT_ORDER = {4: ("red", "green", "blue", "nir"), 3: ("red", "green", "blue")}


def resolve_mode(n_bands, mode=None, bands=None):
    """Decide the mode and where each role sits in the raster.

    Parameters
    ----------
    n_bands : int
        Number of bands in the raster.
    mode : str, optional
        "rgbn", "cir" or "rgb". Default: rgbn for 4 bands, rgb for 3.
        A CIR orthophoto looks like any 3-band raster, so it has to be
        declared.
    bands : sequence of str, optional
        Role of every raster band in raster order, e.g.
        ("nir", "red", "green", "blue"); roles the mode does not use may
        be given as None or any other name. Default: red, green, blue, nir
        for 4 bands; red, green, blue for 3; nir, red, green for mode "cir".

    Returns
    -------
    mode : Mode
    index : dict role -> raster band index (0-based)
    """
    if mode is None:
        mode = "rgbn" if n_bands >= 4 else "rgb"
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {sorted(MODES)}")
    m = MODES[mode]
    if bands is None:
        if mode == "cir":
            bands = ("nir", "red", "green")
        else:
            bands = DEFAULT_ORDER.get(n_bands, DEFAULT_ORDER[4] if n_bands > 4 else None)
        if bands is None or len(bands) > n_bands:
            raise ValueError(f"mode {mode!r} needs {len(m.roles)} bands; the raster has {n_bands}")
    bands = tuple(b.lower() if isinstance(b, str) else None for b in bands)
    if len(bands) > n_bands:
        raise ValueError(f"{len(bands)} band roles given for a raster with {n_bands} bands")
    index = {}
    for role in m.roles:
        if role not in bands:
            raise ValueError(f"mode {mode!r} needs a {role!r} band; got {bands}")
        index[role] = bands.index(role)
    return m, index
