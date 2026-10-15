"""Run one validated, disjoint subset of ROMarrNG's pytest files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

import pytest

ROOT = Path(__file__).resolve().parents[2]


def add_repository_root_to_import_path(root: Path) -> None:
    """Make the candidate package importable without inheriting PYTHONPATH."""
    repository_root = str(root.resolve())
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)


def shard_files(root: Path, letters: str) -> list[str]:
    if re.fullmatch(r"[a-z]+", letters) is None or len(set(letters)) != len(letters):
        raise ValueError("A pytest shard needs unique lowercase filename letters.")
    selected = [
        path.relative_to(root).as_posix()
        for path in sorted(root.glob("tests/test_*.py"))
        if path.name[5:6] in letters
    ]
    if not selected:
        raise ValueError("The pytest shard did not select any test files.")
    return selected


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("letters")
    args = parser.parse_args(argv)
    try:
        files = shard_files(ROOT, args.letters)
    except ValueError as error:
        parser.error(str(error))
    add_repository_root_to_import_path(ROOT)
    return int(pytest.main(["-q", "-p", "no:cacheprovider", *files]))


if __name__ == "__main__":
    raise SystemExit(main())
