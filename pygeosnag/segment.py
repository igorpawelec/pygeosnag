"""Adaptel segmentation of a window in a band mode, via pygeoadaptels."""
import numpy as np


def segment(roles, valid, mode, threshold=None):
    """Adaptels on the mode's bands; -1 on nodata.

    Parameters
    ----------
    roles : dict role -> 2-D array
    valid : bool array (rows, cols)
    mode : Mode
    threshold : float, optional
        Overrides the mode's matched threshold (research only).
    """
    from pygeoadaptels import adaptels_from_array
    data = np.ascontiguousarray(np.stack([np.asarray(roles[r], np.float64) for r in mode.roles]))
    lab, _ = adaptels_from_array(data, mask=~valid,
                                 threshold=float(mode.threshold if threshold is None else threshold),
                                 distance="minkowski")
    lab = np.asarray(lab, np.int32).copy()
    lab[~valid] = -1
    return lab
