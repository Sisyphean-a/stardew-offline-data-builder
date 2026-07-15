from __future__ import annotations

import json
from pathlib import Path

from builder.sources.game_source import load_raw_entities_from_unpacked_dir


def test_load_raw_entities_supports_generic_phase7_types(tmp_path: Path) -> None:
    data_dir = tmp_path / "Data"
    data_dir.mkdir(parents=True)
    payloads = {
        "Monster.zh-CN.json": {
            "entries": [
                {
                    "id": "shadow-brute",
                    "internalName": "ShadowBrute",
                    "name": "暗影蛮兵",
                    "description": "测试怪物",
                }
            ]
        },
        "Weapon.zh-CN.json": {
            "entries": [
                {
                    "id": "rusty-sword",
                    "internalName": "RustySword",
                    "name": "生锈短剑",
                    "description": "测试武器",
                }
            ]
        },
        "Achievement.zh-CN.json": {
            "entries": [
                {
                    "id": "greenhorn",
                    "internalName": "Greenhorn",
                    "name": "新手上路",
                    "description": "测试成就",
                }
            ]
        },
    }

    for filename, payload in payloads.items():
        (data_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    entities = load_raw_entities_from_unpacked_dir(tmp_path)

    assert {(entity.entity_type, entity.source_id) for entity in entities} == {
        ("monster", "shadow-brute"),
        ("weapon", "rusty-sword"),
        ("achievement", "greenhorn"),
    }
