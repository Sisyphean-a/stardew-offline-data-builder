from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_paths(paths: list[Path]) -> str:
    digest = sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        digest.update(path.as_posix().encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def sha256_relative_paths(root: Path, paths: list[Path]) -> str:
    """Hash a file tree by its portable relative paths and bytes."""
    resolved_root = root.resolve()
    digest = sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(resolved_root).as_posix()):
        resolved_path = path.resolve()
        digest.update(resolved_path.relative_to(resolved_root).as_posix().encode("utf-8"))
        if resolved_path.is_file():
            digest.update(resolved_path.read_bytes())
    return digest.hexdigest()
