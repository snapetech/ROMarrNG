"""Request-scoped game directory downloads, without buffering game data."""

from __future__ import annotations

import hashlib
import os
import stat
import tarfile
from pathlib import Path


MAX_GAME_FILES = 10_000


def directory_asset(source: Path, root: Path) -> dict | None:
    """Snapshot a bounded complete tree. Never publish a truncated bundle."""
    members = []
    length = 0
    visited = 0
    for current, dirs, files in os.walk(source, followlinks=False):
        visited += 1
        if visited > MAX_GAME_FILES or len(dirs) + len(files) > MAX_GAME_FILES:
            return None
        dirs[:] = sorted(name for name in dirs
                         if not (Path(current) / name).is_symlink()
                         and not name.startswith(".romarr-import-"))
        for name in sorted(files):
            path = Path(current) / name
            if path.is_symlink():
                continue
            try:
                real = path.resolve(strict=True)
                real.relative_to(root)
                relative = real.relative_to(source).as_posix()
                snapshot = real.stat()
            except (OSError, ValueError):
                return None
            if not stat.S_ISREG(snapshot.st_mode):
                continue
            if len(members) >= MAX_GAME_FILES:
                return None
            info = tarfile.TarInfo(relative)
            info.size = snapshot.st_size
            info.mode = 0o644
            # Fixed metadata keeps the response size stable, hides host users,
            # and avoids timestamp-based PAX records.
            length += len(info.tobuf(format=tarfile.PAX_FORMAT))
            length += ((info.size + 511) // 512) * 512
            members.append((real, info, snapshot))
    if not members:
        return None
    length += 1024
    length = ((length + tarfile.RECORDSIZE - 1) // tarfile.RECORDSIZE) * tarfile.RECORDSIZE
    return {"id": hashlib.sha256(("bundle:" + str(source)).encode()).hexdigest(),
            "name": source.name + ".tar", "size": length,
            "path": source, "members": members}


def stream_directory(asset: dict, output) -> None:
    """Tar streams use bounded buffers and preserve every relative path."""
    with tarfile.open(fileobj=output, mode="w|", format=tarfile.PAX_FORMAT) as archive:
        for path, info, snapshot in asset["members"]:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as handle:
                current = os.fstat(handle.fileno())
                if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
                        snapshot.st_dev, snapshot.st_ino,
                        snapshot.st_size, snapshot.st_mtime_ns):
                    raise OSError("game files changed during download")
                archive.addfile(info, handle)
