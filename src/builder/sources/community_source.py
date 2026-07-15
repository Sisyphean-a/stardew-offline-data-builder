from __future__ import annotations

from pathlib import Path

from builder.models import RawEntity
from builder.parsers.localization import build_raw_entities_from_entries, classify_localized_json
from builder.utils.json_io import load_json_file


def community_data_exists(path: Path) -> bool:
    return path.exists() and path.is_dir()


def load_raw_entities_from_community_dir(community_dir: Path) -> list[RawEntity]:
    entities: list[RawEntity] = []
    for json_file in sorted(community_dir.rglob("*.json")):
        payload = load_json_file(json_file)
        discovered = classify_localized_json(json_file, payload)
        if discovered is None:
            continue
        entries = build_raw_entities_from_entries(
            json_file,
            payload,
            discovered.locale,
            entity_type=discovered.entity_type,
            source="community",
        )
        entities.extend(entries)
    return entities
