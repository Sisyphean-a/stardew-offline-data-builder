from __future__ import annotations

from pathlib import Path

from builder.parsers.localization import infer_entity_type
from builder.sources.game_source import discover_game_json_files


def test_discover_game_json_files_detects_entity_and_shop_assets() -> None:
    discovered = discover_game_json_files(Path("tests/fixtures/game-data/Content (unpacked)"))

    assert len(discovered) == 9
    assert {item.entity_type for item in discovered} == {
        "object",
        "crop",
        "fish",
        "villager",
        "shop",
    }
    assert {item.locale for item in discovered} == {"en", "zh-CN"}


def test_infer_entity_type_supports_phase7_categories() -> None:
    cases = {
        "Monster.zh-CN.json": "monster",
        "Weapon.zh-CN.json": "weapon",
        "Achievement.zh-CN.json": "achievement",
        "Special-Order.zh-CN.json": "special_order",
        "GingerIsland.zh-CN.json": "ginger_island",
        "Shop.zh-CN.json": "shop",
        "Schedule.zh-CN.json": "npc_schedule",
    }

    for filename, entity_type in cases.items():
        assert infer_entity_type(Path(filename)) == entity_type
