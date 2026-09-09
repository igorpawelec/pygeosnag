"""operating_threshold: the band mode's own cut when the manifest has one, else the common one."""
from pygeosnag import assets


def test_per_mode_threshold_falls_back_to_the_common_one(monkeypatch):
    fake = {"operating_point": {"threshold": 0.7, "per_mode": {"rgb": 0.6}}}
    monkeypatch.setattr(assets, "manifest", lambda quiet=False: fake)
    assert assets.operating_threshold(mode="rgb") == 0.6
    assert assets.operating_threshold(mode="rgbn") == 0.7
    assert assets.operating_threshold() == 0.7


def test_missing_manifest_gives_the_default(monkeypatch):
    def boom(quiet=False):
        raise FileNotFoundError("no manifest")
    monkeypatch.setattr(assets, "manifest", boom)
    assert assets.operating_threshold(default=0.5, mode="rgb") == 0.5
