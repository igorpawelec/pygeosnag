"""Scene normalisation of the absolute spectral means.

A scene-wide colour cast (a 2022 flight whose background sits at NDGR 0.20
and chroma 10 where the training sites sit at 0.06-0.10 and 6-8) moves the
absolute adaptel means (sr.NDVI, sr.NDGR, sr.NDBR, sr.L, sr.C) to where the
forest has learnt background; the contrast (ktr.*) and spread (sd.*)
features are cast-free by construction. Measured leave-one-site-out on
eight sites (assets v2): replacing every sr.* by its z-score within the
scene -- median and MAD over all adaptels of the scene, no labels -- took
the worst site from F1 0.12 to 0.61 and the pooled F1 from 0.58 to 0.61.

The statistics are the scene's, so they have to be gathered before any
tile is scored: `fit_from_samples` takes the feature tables of a sample of
tiles; `apply` transforms one tile's table. The manifest of a forest says
whether it was trained with such a transform ("feature_transform") and on
which columns; `from_manifest_entry` reads that.

  type "zsr"   the sr.* columns are replaced by their z-scores
  type "both"  the z-scores are appended after the original columns
"""
import numpy as np


class SceneNorm:
    def __init__(self, kind, columns, names):
        if kind not in ("zsr", "both"):
            raise ValueError(f"unknown feature transform {kind!r}")
        self.kind = kind
        self.columns = list(columns)
        self.idx = [names.index(c) for c in self.columns]
        self.med = None
        self.mad = None

    @classmethod
    def from_manifest_entry(cls, entry, names):
        ft = (entry or {}).get("feature_transform")
        if not ft:
            return None
        return cls(ft["type"], ft["columns"], names)

    def fit_from_samples(self, tables):
        """Median and MAD of the transformed columns over the pooled tables."""
        X = np.vstack([t[:, self.idx] for t in tables if len(t)]).astype(np.float64)
        X = np.where(np.isfinite(X), X, np.nan)
        self.med = np.nanmedian(X, axis=0)
        self.mad = np.nanmedian(np.abs(X - self.med), axis=0) * 1.4826 + 1e-6
        return self

    def set(self, med, mad):
        self.med, self.mad = np.asarray(med, float), np.asarray(mad, float)
        return self

    @property
    def fitted(self):
        return self.med is not None

    def apply(self, X):
        if not self.fitted:
            raise RuntimeError("SceneNorm not fitted")
        X = np.asarray(X, np.float32)
        z = ((X[:, self.idx] - self.med) / self.mad).astype(np.float32)
        if self.kind == "zsr":
            out = X.copy()
            out[:, self.idx] = z
            return out
        return np.column_stack([X, z]).astype(np.float32)

    def output_names(self, names):
        if self.kind == "zsr":
            return list(names)
        return list(names) + [f"z.{c}" for c in self.columns]

    def describe(self):
        return ", ".join(f"{c}: med {m:.3f} mad {s:.3f}" for c, m, s in zip(self.columns, self.med, self.mad))
