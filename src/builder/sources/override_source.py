from __future__ import annotations

from pathlib import Path

from builder.utils.json_io import load_json_file


def load_aliases(path: Path) -> dict[str, list[str]]:
    payload = load_json_file(path)
    return {key: [str(item) for item in value] for key, value in dict(payload).items()}


def load_categories(path: Path) -> dict[str, str]:
    payload = load_json_file(path)
    return {key: str(value) for key, value in dict(payload).items()}


def load_entity_overrides(path: Path) -> dict[str, dict[str, object]]:
    payload = dict(load_json_file(path))
    records = payload.get("entity_overrides", {})
    if not isinstance(records, dict):
        raise ValueError("entity_overrides 必须是对象")
    return {
        str(entity_id): dict(values)
        for entity_id, values in records.items()
        if isinstance(values, dict)
    }
