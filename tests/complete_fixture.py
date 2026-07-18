from __future__ import annotations

import json
from pathlib import Path

from builder.config import REQUIRED_ENTITY_TYPES
from builder.sources.game_source import load_raw_entities_from_unpacked_dir


def add_required_entity_baseline(unpacked_dir: Path) -> None:
    existing = {entity.entity_type for entity in load_raw_entities_from_unpacked_dir(unpacked_dir)}
    for entity_type in sorted(set(REQUIRED_ENTITY_TYPES) - existing):
        write_entity_fixture(unpacked_dir, entity_type, "en", f"Fixture {entity_type}")
        write_entity_fixture(unpacked_dir, entity_type, "zh-CN", f"测试{entity_type}")


def write_entity_fixture(unpacked_dir: Path, entity_type: str, locale: str, name: str) -> None:
    payload = {
        "entityType": entity_type,
        "locale": locale,
        "entries": [
            {
                "id": f"fixture-{entity_type}",
                "internalName": f"Fixture{entity_type}",
                "name": name,
                "description": f"Fixture {entity_type} description.",
            }
        ],
    }
    path = unpacked_dir / "Data" / f"fixture-{entity_type}.{locale}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
