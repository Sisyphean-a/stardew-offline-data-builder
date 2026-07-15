from __future__ import annotations

from pathlib import Path

from builder.utils.json_io import load_json_file


def load_aliases(path: Path) -> dict[str, list[str]]:
    payload = load_json_file(path)
    return {key: [str(item) for item in value] for key, value in dict(payload).items()}


def load_categories(path: Path) -> dict[str, str]:
    payload = load_json_file(path)
    return {key: str(value) for key, value in dict(payload).items()}


def load_match_overrides(path: Path) -> dict[str, str]:
    payload = load_json_file(path)
    mappings = dict(payload).get("match_overrides", {})
    return {str(key): str(value) for key, value in dict(mappings).items()}
