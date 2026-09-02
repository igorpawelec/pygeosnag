"""Per-adaptel features, exactly as the forests were trained.

Twenty features in the RGBN mode: for each of NDVI, NDGR, NDBR, CIELCh
lightness L and chroma C the adaptel mean, standard deviation and
contrast (mean minus the mean of a 25 m box around each pixel, averaged
over the adaptel); the circular mean of hue as cosine and sine and its
circular variance; area in m2 and elongation from the pixel covariance.
The RGB mode drops the NDVI triple, the CIR mode drops the NDBR triple.

Every constant here is part of the model: 0.25 m pixels, a 25 m context
box (101 px), a 4-pixel floor below which an adaptel is not scored, hue
from the RGB -> CIELCh transform of pygeopalette applied to (R, G, B) or,
in the CIR mode, to (NIR, R, G) as if it were RGB.
"""
import numpy as np
from scipy.ndimage import uniform_filter

GSD = 0.25                       # m per pixel the forests were trained at
CTX_M = 25.0                     # side of the context box, m
MIN_PX = 4                       # adaptels smaller than this are not scored
K = 2 * int(CTX_M / GSD / 2) + 1  # 101 px: an odd box, centred on the pixel, as trained

_INDEX_BANDS = {"NDVI": ("nir", "red"), "NDGR": ("green", "red"), "NDBR": ("blue", "red")}


def feature_names(mode):
    """Feature names of a mode, in column order (research names kept)."""
    names = []
    for nm in tuple(mode.indices) + ("L", "C"):
        names += [f"sr.{nm}", f"sd.{nm}", f"ktr.{nm}"]
    names += ["cos.Hab", "sin.Hab", "war.Hab", "pow.m2", "wydluzenie"]
    return names


from .modes import MODES  # noqa: E402

FEATURE_NAMES = {k: feature_names(m) for k, m in MODES.items()}


def to_uint8(band):
    """Bands as the forests saw them: 8-bit reflectance-like values.

    8-bit data pass through. Anything above 255 (16-bit orthophotos) is
    scaled linearly so that its 99.9th percentile lands at 255 -- a
    guess, and the reason to prefer 8-bit input; a warning says so.
    """
    band = np.asarray(band, np.float32)
    finite = band[np.isfinite(band)]
    if finite.size and finite.max() > 255:
        import warnings
        hi = float(np.percentile(finite, 99.9))
        warnings.warn(f"band values reach {finite.max():.0f}; scaling 99.9th percentile {hi:.0f} to 255 "
                      "(the models were trained on 8-bit orthophotos)")
        band = band * (255.0 / max(hi, 1.0))
    return np.clip(band, 0, 255)


def lch_of(roles, mode):
    """CIELCh from the mode's RGB-like trio, via pygeopalette."""
    import pygeopalette as gp
    trio = [np.clip(roles[r], 0, 255).astype(np.uint8) for r in mode.lch_trio]
    comps, names = gp.convertbands(trio[0], trio[1], trio[2], "lchab")
    return dict(zip(names, (np.asarray(c, np.float64) for c in comps)))


def local_mean(band, valid, k=K):
    """Mean over a k x k box, nodata excluded, edges by nearest."""
    b = np.where(valid, band, 0.0)
    return (uniform_filter(b, k, mode="nearest")
            / np.maximum(uniform_filter(valid.astype(np.float64), k, mode="nearest"), 1e-6))


def segment_features(seg, roles, valid, lch, mode):
    """Feature table of every segment of a window.

    Parameters
    ----------
    seg : int array (rows, cols)
        Segment labels, -1 (or anything) on nodata; only `valid` pixels count.
    roles : dict role -> 2-D float array
        Bands by role ("red", "green", "blue", "nir"); a mode uses its own.
    valid : bool array (rows, cols)
    lch : dict with "L", "C", "Hab" (float64 arrays), from lch_of().
    mode : Mode

    Returns
    -------
    X : float32 (n_segments, n_features)
    lab : int64 labels of the valid pixels, re-based to start at 0
    cnt : float pixel count per segment
    mr, mc : float mean row and column per segment
    """
    lab = seg[valid].astype(np.int64)
    base = lab.min()
    lab -= base
    n_lab = int(lab.max()) + 1
    cnt = np.bincount(lab, minlength=n_lab).astype(float)
    den = np.maximum(cnt, 1)
    bands = []
    for nm in mode.indices:
        a, b = (roles[r].astype(np.float64) for r in _INDEX_BANDS[nm])
        bands.append((nm, (a - b) / np.maximum(a + b, 1e-6)))
    bands += [("L", lch["L"]), ("C", lch["C"])]
    cols = []
    for nm, band in bands:
        v = band[valid]
        m = np.bincount(lab, weights=v, minlength=n_lab) / den
        sq = np.bincount(lab, weights=v * v, minlength=n_lab) / den
        lm = local_mean(band, valid)[valid]
        cols += [m, np.sqrt(np.maximum(sq - m * m, 0)),
                 m - np.bincount(lab, weights=lm, minlength=n_lab) / den]
    th = np.deg2rad(lch["Hab"][valid])
    mc_ = np.bincount(lab, weights=np.cos(th), minlength=n_lab) / den
    ms_ = np.bincount(lab, weights=np.sin(th), minlength=n_lab) / den
    cols += [mc_, ms_, 1 - np.sqrt(mc_ * mc_ + ms_ * ms_)]
    ri, ci = np.nonzero(valid)
    mr = np.bincount(lab, weights=ri.astype(float), minlength=n_lab) / den
    mc = np.bincount(lab, weights=ci.astype(float), minlength=n_lab) / den
    vrr = np.bincount(lab, weights=(ri - mr[lab]) ** 2, minlength=n_lab) / den
    vcc = np.bincount(lab, weights=(ci - mc[lab]) ** 2, minlength=n_lab) / den
    vrc = np.bincount(lab, weights=(ri - mr[lab]) * (ci - mc[lab]), minlength=n_lab) / den
    t_ = vrr + vcc
    dt = np.maximum(t_ * t_ / 4 - (vrr * vcc - vrc * vrc), 0)
    l1, l2 = t_ / 2 + np.sqrt(dt), np.maximum(t_ / 2 - np.sqrt(dt), 1e-9)
    cols += [cnt * GSD * GSD, np.sqrt(l1 / l2)]
    return np.column_stack(cols).astype(np.float32), lab, cnt, mr, mc


def edges_of(seg, valid):
    """Unique 4-neighbour adjacencies between segments, re-based like the labels."""
    base = seg[valid].min()
    a, b = seg[:, :-1], seg[:, 1:]
    m1 = (a != b) & (a >= 0) & (b >= 0)
    a2, b2 = seg[:-1, :], seg[1:, :]
    m2 = (a2 != b2) & (a2 >= 0) & (b2 >= 0)
    e = np.vstack([np.column_stack([a[m1], b[m1]]),
                   np.column_stack([a2[m2], b2[m2]])]) - base
    return np.unique(np.sort(e, axis=1), axis=0)
