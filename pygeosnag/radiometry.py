"""Per-band radiometric matching of a scene to the training orthophotos.

The forests were trained on 8-bit orthophotos whose per-band 2nd and 98th
percentiles sit in a narrow corridor (the medians over the nine training
rasters are the REFERENCE below). A hazy or flat scene -- the whole
histogram shifted up and squeezed -- keeps its ranking of dark and bright
crowns, but every contrast the forests learnt on (the CIELCh lightness
and chroma, the spread and contrast features) comes out smaller, and the
adaptel probabilities never reach the operating point. Measured on a
Radom 2017 pine scene with red 56-123 and NIR 57-119 (reference 29-80 and
50-144): the highest probability on a 600 m crop was 0.23; mapped onto the
reference range, the same crop gave 11 points above 0.6 that sit on grey
crowns. Scene normalisation (scenenorm.py) does not cover this: it
standardises the five absolute means, not the pixel-level contrasts.

``Radiometry`` maps the scene's 2-98 percentile of every band linearly
onto the reference 2-98 percentile. ``kind="auto"`` does that only when
the scene is off: a dark end more than 15 DN above the reference (haze)
or a range narrower than 0.7 of the reference; ``"match"`` always;
``"off"`` never. The percentiles come from the same sampled tiles the
scene normalisation uses, valid pixels only.

It is a rescue, not a default. On the 200-scene batch of 2026-09-07 the
"auto" trigger fired on 44 scenes: 27 went from nothing to hundreds of
points, 17 lost nearly everything (one from 27 000 points to 159). Mapping
the bands separately changes the ratios between them -- NDVI, NDGR, NDBR
-- and the forests stand on those. A scene the default run handles is
left alone; the mapping is for the scene where it finds nothing.
"""
import numpy as np

# median 2nd / 98th percentile per band over the nine training rasters
# (krynki1, krynki2, gleboczek, niedzwiedzi, ocwieka, szczepanowo, kudypy,
# mieszkowice, bpn; measured 2026-09-07 at 4 m on valid pixels)
REFERENCE = {"red": (29.0, 80.0), "green": (45.0, 94.0), "blue": (55.0, 79.0), "nir": (50.0, 144.0)}
OFFSET_DN = 15.0          # dark end this much above the reference -> haze
RANGE_RATIO = 0.7         # range this much narrower than the reference -> flat


class Radiometry:
    def __init__(self, kind="auto", lo=2.0, hi=98.0, reference=None):
        if kind not in ("auto", "match", "off"):
            raise ValueError(f"radiometry kind {kind!r}; choose auto, match or off")
        self.kind = kind
        self.lo, self.hi = float(lo), float(hi)
        self.reference = dict(reference or REFERENCE)
        self.scene = {}           # role -> (p_lo, p_hi) measured on the scene
        self.active = False
        self.reasons = []
        self.fitted = False

    def fit(self, samples):
        """samples: dict role -> 1-D array of valid pixel values pooled over the sampled tiles."""
        self.scene = {}
        for role, v in samples.items():
            v = np.asarray(v, np.float64)
            v = v[np.isfinite(v)]
            if v.size < 1000:
                continue
            self.scene[role] = tuple(np.percentile(v, [self.lo, self.hi]))
        self.reasons = []
        for role, (s_lo, s_hi) in self.scene.items():
            if role not in self.reference:
                continue
            r_lo, r_hi = self.reference[role]
            if s_lo - r_lo > OFFSET_DN:
                self.reasons.append(f"{role} dark end {s_lo:.0f} vs {r_lo:.0f}")
            if (s_hi - s_lo) < RANGE_RATIO * (r_hi - r_lo):
                self.reasons.append(f"{role} range {s_hi - s_lo:.0f} vs {r_hi - r_lo:.0f}")
        self.active = self.kind == "match" or (self.kind == "auto" and bool(self.reasons))
        self.fitted = True
        return self

    def apply(self, band_roles):
        """dict role -> 2-D array (any dtype, 0-255 expected) -> same dict, mapped and clipped."""
        if not self.active:
            return band_roles
        out = {}
        for role, a in band_roles.items():
            if role in self.scene and role in self.reference:
                s_lo, s_hi = self.scene[role]
                r_lo, r_hi = self.reference[role]
                scale = (r_hi - r_lo) / max(s_hi - s_lo, 1e-6)
                b = (np.asarray(a, np.float32) - s_lo) * scale + r_lo
                out[role] = np.clip(b, 0.0, 255.0)
            else:
                out[role] = a
        return out

    def describe(self):
        if not self.fitted:
            return "not fitted"
        mapping = ", ".join(f"{r} {s[0]:.0f}-{s[1]:.0f} -> {self.reference[r][0]:.0f}-{self.reference[r][1]:.0f}"
                            for r, s in self.scene.items() if r in self.reference)
        if self.active:
            why = "; ".join(self.reasons) if self.reasons else "forced"
            return f"matched to the training range ({why}): {mapping}"
        return f"within the training range, untouched ({mapping})"
