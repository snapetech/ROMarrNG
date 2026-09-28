import io
import tarfile
import zipfile

import pytest

from romarr.app import ROMarr, _seerr_local_assets, _seerr_library_lookup
from romarr.dat import hash_bytes, hash_stream
from romarr.game_assets import directory_asset, stream_directory
from romarr.libraries import FolderConfig, FolderLibrary
from romarr.library import import_rom, is_safe_name
from romarr.platforms import by_slug, resolve
from romarr.selection import Release, judge, pick_all_rom_sets
from romarr.store import QueueItem, SeerrRequest


@pytest.mark.parametrize("name,slug", [
    ("PlayStation 4", "ps4"), ("Sony PlayStation 5", "ps5"),
    ("PlayStation Vita", "psvita"), ("Microsoft Xbox One", "xboxone"),
    ("Xbox Series X/S", "series-x-s"), ("Xbox Series X|S", "series-x-s"),
    ("Xbox Series X", "series-x-s"), ("Xbox Series S", "series-x-s"),
])
def test_recent_console_names_resolve_exactly(name, slug):
    assert resolve(name).slug == slug


@pytest.mark.parametrize("slug,label,extension", [
    ("ps4", "PS4", ".pkg"), ("ps5", "PS5", ".pkg"),
    ("psvita", "PlayStation Vita", ".vpk"),
    ("xboxone", "Xbox One", ".xvc"),
    ("series-x-s", "Xbox Series X/S", ".xvc"),
])
def test_shared_packages_require_a_console_label(slug, label, extension):
    platform = by_slug(slug)
    def release(title):
        return Release(title, size=8 << 30, seeders=10, categories=(1030,),
                       download_url="magnet:?xt=urn:btih:test", protocol="torrent")
    assert judge(release("Test Game " + label), "Test Game", platform).accepted
    assert not judge(release("Test Game" + extension), "Test Game", platform).accepted
    assert not judge(release("Test Game PC CODEX"), "Test Game", platform).accepted
    assert pick_all_rom_sets(["Test Game" + extension], platform)[0].primary.endswith(extension)


@pytest.mark.parametrize("slug,label", [
    ("ps4", "PS5"), ("ps5", "PS4"), ("xbox", "Xbox One"),
    ("xbox", "Xbox Series S"), ("xboxone", "Xbox Series X/S"),
    ("series-x-s", "Xbox One"), ("psx", "PlayStation Vita"),
])
def test_wrong_generation_never_wins(slug, label):
    assert not judge(Release("Test Game " + label, size=8 << 30, seeders=100,
                            categories=(1030,), download_url="magnet:?xt=urn:btih:test",
                            protocol="torrent"),
                     "Test Game", by_slug(slug)).accepted


@pytest.mark.parametrize("slug,files", [
    ("ps3", ["PS3_GAME/USRDIR/EBOOT.BIN", "PS3_GAME/PARAM.SFO", "PS3_GAME/USRDIR/assets/a.bin"]),
    ("ps4", ["eboot.bin", "sce_sys/param.sfo", "assets/a.bin", "other/a.bin", "sce_sys/icon0.png"]),
    ("ps5", ["eboot.bin", "sce_sys/param.json", "assets/a.bin", "other/a.bin"]),
    ("psvita", ["eboot.bin", "sce_sys/param.sfo", "data/a.bin"]),
])
@pytest.mark.parametrize("archived", [False, True])
@pytest.mark.parametrize("layout", ["flat", "nested"])
def test_complete_folder_import_and_library_readback(tmp_path, slug, files, archived, layout):
    download = tmp_path / "Test Game"
    if archived:
        download = download.with_suffix(".zip")
        with zipfile.ZipFile(download, "w") as archive:
            for name in files:
                archive.writestr("Test Game/" + name, b"game")
    else:
        for name in files:
            path = download / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"game")
    root = tmp_path / "library"
    [result] = import_rom(download, by_slug(slug), root, layout=layout)
    assert result.ok, result.reason
    platform_root = root / slug / "roms" if layout == "nested" else root / slug
    assert result.destination == platform_root / "Test Game"
    for name in files:
        assert (result.destination / name).read_bytes() == b"game"
    library = FolderLibrary(FolderConfig(root=str(root)))
    [game] = library.games()
    assert (game.name, game.platform, game.id) == ("Test Game", slug, str(result.destination))
    assert library.count() == 1


def test_incomplete_and_wrong_generation_dumps_are_rejected():
    assert not pick_all_rom_sets(["eboot.bin"], by_slug("ps4"))
    assert not pick_all_rom_sets(["eboot.bin", "sce_sys/param.json"], by_slug("ps4"))
    assert not pick_all_rom_sets(["eboot.bin", "sce_sys/param.sfo"], by_slug("ps5"))


def test_adjacent_games_remain_separate():
    files = [root + name for root in ("One/", "Two/")
             for name in ("eboot.bin", "sce_sys/param.json", "data.bin")]
    sets = pick_all_rom_sets(files, by_slug("ps5"))
    assert [game.root for game in sets] == ["One/", "Two/"]
    assert all(len(game.members) == 3 for game in sets)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:\\escape", "dir/../escape", "bad\x00name"])
def test_unsafe_game_members_are_refused(tmp_path, name):
    assert not is_safe_name(name, tmp_path)


def test_rejected_import_does_not_publish_partial_game(tmp_path):
    source = tmp_path / "bad.zip"
    with zipfile.ZipFile(source, "w") as archive:
        for name in ("eboot.bin", "sce_sys/param.json", "data/File.bin", "data/file.bin"):
            archive.writestr(name, b"game")
    [result] = import_rom(source, by_slug("ps5"), tmp_path / "library")
    assert not result.ok
    assert not result.destination.exists()


def test_api_exposes_aliases_and_does_not_invent_playability(tmp_path):
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "state.json")})
    rows = {row["slug"]: row for row in service.platform_directory()}
    assert "nintendo entertainment system" in rows["nes"]["aliases"]
    for slug in ("ps4", "ps5", "xboxone", "series-x-s"):
        assert rows[slug]["aliases"]
        assert rows[slug]["play_routes"] == ["download"]
        assert not rows[slug]["plays"]


def test_directory_bundle_contains_more_than_one_hundred_files(tmp_path):
    game = tmp_path / "Test Game"
    for number in range(120):
        path = game / "assets" / f"{number}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"game data")
    asset = directory_asset(game, tmp_path)
    output = io.BytesIO()
    stream_directory(asset, output)
    assert len(output.getvalue()) == asset["size"]
    with tarfile.open(fileobj=io.BytesIO(output.getvalue())) as archive:
        assert len(archive.getnames()) == 120
        assert archive.extractfile("assets/119.bin").read() == b"game data"


def test_bundle_skips_symlinks_and_refuses_changed_files(tmp_path):
    game = tmp_path / "Game"
    game.mkdir()
    data = game / "data.bin"
    data.write_bytes(b"game")
    (game / "link").symlink_to(tmp_path / "secret")
    asset = directory_asset(game, tmp_path)
    assert len(asset["members"]) == 1
    data.write_bytes(b"changed")
    with pytest.raises(OSError, match="changed"):
        stream_directory(asset, io.BytesIO())


def test_bundle_never_silently_truncates(tmp_path, monkeypatch):
    monkeypatch.setattr("romarr.game_assets.MAX_GAME_FILES", 1)
    (tmp_path / "one").write_bytes(b"1")
    (tmp_path / "two").write_bytes(b"2")
    assert directory_asset(tmp_path, tmp_path) is None


def test_stream_hashes_match_bytes_without_large_reads():
    data = b"a" * 2000000
    class Bounded(io.BytesIO):
        def read(self, size=-1):
            assert 0 <= size <= 1024 * 1024
            return super().read(size)
    assert hash_stream(Bounded(data), size=len(data)) == hash_bytes(data)


def test_imported_destinations_survive_restart_and_title_id_names(tmp_path, monkeypatch):
    root = tmp_path / "library"
    game = root / "ps5" / "PPSA12345"
    game.mkdir(parents=True)
    (game / "eboot.bin").write_bytes(b"game")
    state = tmp_path / "state.json"
    service = ROMarr({"ROMARR_DATA": str(state)})
    service.queue.append(QueueItem("Catalog Game", "ps5", "Catalog.Game.PS5",
                                  10, "imported", external_request_id="seerr-1",
                                  imported_paths=[str(game)]))
    service.store.save()
    restarted = ROMarr({"ROMARR_DATA": str(state)})
    monkeypatch.setattr(restarted, "library_for", lambda _: ({"path": str(root)}, None))
    monkeypatch.setattr(restarted, "library_view", lambda **_: {"items": []})
    [asset] = _seerr_local_assets(restarted, SeerrRequest("seerr-1", "Catalog Game", "ps5"))
    assert asset["name"] == "PPSA12345.tar"
    assert _seerr_local_assets(restarted, SeerrRequest("seerr-2", "Catalog Game", "ps5")) == []
    lookup = _seerr_library_lookup(restarted, [{"title": "Catalog Game", "platform": "ps5"}])
    assert lookup["matches"] == [{"title": "Catalog Game", "platform": "ps5"}]


def test_failed_copy_keeps_previous_game_and_removes_staging(tmp_path, monkeypatch):
    from romarr.library import _PathSource
    download = tmp_path / "Game"
    for name in ("eboot.bin", "sce_sys/param.json"):
        path = download / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"new")
    root = tmp_path / "library"
    previous = root / "ps5" / "Game"
    previous.mkdir(parents=True)
    (previous / "old.bin").write_bytes(b"old")
    def fail(*_):
        raise OSError("disk full")
    monkeypatch.setattr(_PathSource, "copy", fail)
    [result] = import_rom(download, by_slug("ps5"), root, overwrite=True)
    assert not result.ok
    assert (previous / "old.bin").read_bytes() == b"old"
    assert not list(root.rglob(".romarr-import-*"))


def test_seven_zip_directory_is_imported_as_one_complete_tree(tmp_path):
    import shutil
    import subprocess
    tool = shutil.which("bsdtar")
    if not tool:
        pytest.skip("libarchive tool unavailable")
    source = tmp_path / "source"
    for name in ("eboot.bin", "sce_sys/param.json", "data/a.bin"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"game")
    archive = tmp_path / "Game.7z"
    subprocess.run([tool, "--format=7zip", "-cf", str(archive), "-C", str(source), "."], check=True)
    [result] = import_rom(archive, by_slug("ps5"), tmp_path / "library")
    assert result.ok, result.reason
    assert (result.destination / "data/a.bin").read_bytes() == b"game"


def test_download_import_records_the_actual_request_destinations(tmp_path, monkeypatch):
    from types import SimpleNamespace
    source = tmp_path / "PPSA12345"
    for name in ("eboot.bin", "sce_sys/param.json", "assets/a.bin"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"game")
    service = ROMarr({"ROMARR_DATA": str(tmp_path / "state.json")})
    service.clients = [SimpleNamespace(configured=True, completed=lambda: [
        {"name": "Catalog.Game.PS5", "content_path": str(source)},
    ])]
    service.queue.append(QueueItem("Catalog Game", "ps5", "Catalog.Game.PS5", 10,
                                  "grabbed", external_request_id="seerr-1"))
    root = tmp_path / "library"
    monkeypatch.setattr(service, "library_for", lambda _: (
        {"path": str(root)}, SimpleNamespace(rescan=lambda _: True)))
    monkeypatch.setattr(service, "notify", lambda _: None)
    [result] = service.import_finished()
    assert result["ok"]
    assert service.queue[0].state == "imported"
    assert service.queue[0].imported_paths == [str(root / "ps5" / "PPSA12345")]
    [asset] = _seerr_local_assets(service, SeerrRequest("seerr-1", "Catalog Game", "ps5"))
    assert len(asset["members"]) == 3
