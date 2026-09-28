"""Request-scoped game directory downloads, without buffering game data."""

from __future__ import annotations

import hashlib
import os
import re
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


def bundle_range(value: str, size: int) -> tuple[int, int, int]:
    if not value:
        return 0, size - 1, 200
    if len(value) > 256:
        raise ValueError("invalid range")
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or not any(match.groups()):
        raise ValueError("invalid range")
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(size - 1, int(last)) if last else size - 1
    else:
        suffix = int(last)
        if suffix <= 0:
            raise ValueError("invalid range")
        start, end = max(0, size - suffix), size - 1
    if start >= size or end < start:
        raise ValueError("unsatisfiable range")
    return start, end, 206


def stream_directory(asset: dict, output, *, start=0, end=None) -> None:
    """Stream a deterministic TAR or range, seeking over unrequested bytes."""
    end = asset["size"] - 1 if end is None else end
    position = 0

    def write_segment(data):
        nonlocal position
        first = max(0, start - position)
        last = min(len(data), end - position + 1)
        if first < last:
            output.write(data[first:last])
        position += len(data)

    for path, info, snapshot in asset["members"]:
        if position > end:
            return
        write_segment(info.tobuf(format=tarfile.PAX_FORMAT))
        first = max(0, start - position)
        last = min(info.size, end - position + 1)
        if first < last:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as handle:
                current = os.fstat(handle.fileno())
                if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
                        snapshot.st_dev, snapshot.st_ino,
                        snapshot.st_size, snapshot.st_mtime_ns):
                    raise OSError("game files changed during download")
                handle.seek(first)
                remaining = last - first
                while remaining:
                    data = handle.read(min(1024 * 1024, remaining))
                    if not data:
                        raise OSError("game file ended during download")
                    output.write(data)
                    remaining -= len(data)
        position += info.size
        write_segment(b"\0" * ((-info.size) % 512))
    # Two EOF blocks and record padding, byte-for-byte like tarfile's stream.
    write_segment(b"\0" * (asset["size"] - position))
