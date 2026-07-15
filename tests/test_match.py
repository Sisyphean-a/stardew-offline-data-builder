from __future__ import annotations

from pathlib import Path

from builder.sources.game_source import discover_game_json_files


def test_discover_game_json_files_detects_four_entity_types() -> None:
    discovered = discover_game_json_files(Path("tests/fixtures/game-data/Content (unpacked)"))

    assert len(discovered) == 8
    assert {item.entity_type for item in discovered} == {"object", "crop", "fish", "villager"}
    assert {item.locale for item in discovered} == {"en", "zh-CN"}
