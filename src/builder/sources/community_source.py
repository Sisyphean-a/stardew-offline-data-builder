from __future__ import annotations

from pathlib import Path


def community_data_exists(path: Path) -> bool:
    return path.exists() and path.is_dir()
