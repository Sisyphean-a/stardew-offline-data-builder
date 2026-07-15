from __future__ import annotations

from pathlib import Path

from builder.pipeline.normalize import normalize_entities
from builder.sources.game_source import load_raw_entities_from_unpacked_dir


def test_normalize_fixture_entities() -> None:
    raw_entities = load_raw_entities_from_unpacked_dir(
        Path("tests/fixtures/game-data/Content (unpacked)")
    )

    entities = normalize_entities(
        raw_entities,
        aliases={"object:24": ["萝卜"]},
        categories={"object:24": "作物"},
    )

    assert {entity.id for entity in entities} == {
        "object:24",
        "crop:kale-seeds",
        "fish:sturgeon",
        "villager:Abigail",
    }

    object_entity = next(entity for entity in entities if entity.id == "object:24")
    assert object_entity.name_zh == "防风草"
    assert object_entity.name_en == "Parsnip"
