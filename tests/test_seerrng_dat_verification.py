"""DAT verdicts reported on SeerrNG-delivered files."""

from romarr.app import ROMarr, _seerr_local_assets
from romarr.hashes import HashIndex
from romarr.store import QueueItem, SeerrRequest


def test_hash_index_reports_verdict_by_path(tmp_path):
    index = HashIndex(tmp_path / "hashes.json")
    index.add("A" * 40, "Good Game", "snes", True, "/lib/snes/Good.sfc")
    index.add("b" * 40, "Homebrew", "snes", False, "/lib/snes/Homebrew.sfc")
    assert index.verified_for_path("/lib/snes/Good.sfc") is True
    assert index.verified_for_path("/lib/snes/Homebrew.sfc") is False
    assert index.verified_for_path("/lib/snes/Unknown.sfc") is None
    # The first spelling the index knows answers.
    assert index.verified_for_path("/elsewhere", "/lib/snes/Good.sfc") is True

    index.save()
    reloaded = HashIndex(tmp_path / "hashes.json")
    reloaded.load()
    assert reloaded.verified_for_path("/lib/snes/Good.sfc") is True

    index.clear_platform("snes")
    assert index.verified_for_path("/lib/snes/Good.sfc") is None


def test_seerrng_assets_include_dat_verdict(tmp_path, monkeypatch):
    root = tmp_path / "library"
    (root / "snes").mkdir(parents=True)
    good = root / "snes" / "Good.sfc"
    unknown = root / "snes" / "Hack.sfc"
    good.write_bytes(b"good")
    unknown.write_bytes(b"hack")
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "state.json")})
    service.queue.append(QueueItem(
        "Good Game", "snes", "Good.Game.SNES", 10, "imported",
        external_request_id="seerr-1",
        imported_paths=[str(good), str(unknown)]))
    service.hashes.add("c" * 40, "Good Game", "snes", True, str(good))
    monkeypatch.setattr(service, "library_for",
                        lambda _: ({"path": str(root)}, None))

    assets = _seerr_local_assets(
        service, SeerrRequest("seerr-1", "Good Game", "snes"))
    by_name = {asset["name"]: asset["datVerified"] for asset in assets}
    assert by_name == {"Good.sfc": True, "Hack.sfc": None}
