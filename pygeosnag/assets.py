"""The frozen models and the pooled feature table: where they live and
how they are fetched.

They are release assets of the GitHub repository, not part of the wheel
(the RGBN forest alone is ~40 MB). On first use they are downloaded into
a cache directory and verified against the sha256 in the manifest.

Locations, in order:
1. the directory in PYGEOSNAG_ASSETS, if set (nothing is downloaded there);
2. ~/.cache/pygeosnag/<release>/, filled on demand.
"""
import hashlib
import json
import os
import urllib.request

RELEASE = "assets-v1"
URL = f"https://github.com/igorpawelec/pygeosnag/releases/download/{RELEASE}/{{name}}"
KEYS = {"rgbn": "segments_rgbn", "cir": "segments_cir", "rgb": "segments_rgb", "objects": "objects_rgbn"}


def assets_dir():
    d = os.environ.get("PYGEOSNAG_ASSETS")
    if d:
        return d
    d = os.path.join(os.path.expanduser("~"), ".cache", "pygeosnag", RELEASE)
    os.makedirs(d, exist_ok=True)
    return d


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(name, quiet=False):
    d = assets_dir()
    path = os.path.join(d, name)
    if os.path.exists(path):
        return path
    if os.environ.get("PYGEOSNAG_ASSETS"):
        raise FileNotFoundError(f"{name} not found in PYGEOSNAG_ASSETS={d}")
    if not quiet:
        print(f"pygeosnag: downloading {name} ...", flush=True)
    url = URL.format(name=name)
    try:
        urllib.request.urlretrieve(url, path + ".part")
    except Exception as e:
        try:
            os.remove(path + ".part")
        except OSError:
            pass
        raise RuntimeError(
            f"pygeosnag: could not download {name} from {url} ({e}). The models are release "
            f"assets of the pygeosnag repository; if the release is not published yet or the "
            f"machine is offline, set PYGEOSNAG_ASSETS to a folder that holds manifest.json and "
            f"the model files (in QGIS: the 'Local models folder' parameter).") from e
    os.replace(path + ".part", path)
    return path


def manifest(quiet=False):
    with open(_fetch("manifest.json", quiet), encoding="utf-8") as f:
        return json.load(f)


def asset_path(key, quiet=False, verify=True):
    """Local path of a manifest entry (e.g. "segments_rgbn"), downloaded if needed."""
    m = manifest(quiet)
    if key not in m["files"]:
        raise KeyError(f"{key!r} not in the asset manifest; keys: {sorted(m['files'])}")
    entry = m["files"][key]
    path = _fetch(entry["path"], quiet)
    if verify and _sha256(path) != entry["sha256"]:
        raise RuntimeError(f"{path} does not match the manifest checksum; delete it and retry")
    return path


def load_forest(key, quiet=False):
    """A scikit-learn forest: "rgbn", "cir", "rgb" (segments) or "objects"."""
    import joblib
    return joblib.load(asset_path(KEYS.get(key, key), quiet))


def feature_table(mode, quiet=False):
    """Pooled sample feature table of a mode: X (float32), y (bool), site (int8)."""
    import numpy as np
    z = np.load(asset_path(f"features_{mode}", quiet))
    return z["X"], z["y"], z["site"]
