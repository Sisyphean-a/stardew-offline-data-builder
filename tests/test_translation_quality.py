from __future__ import annotations

from builder.models import RawEntity
from builder.pipeline.normalize import normalize_entities


def test_numeric_localized_name_is_invalid_not_complete() -> None:
    entities = normalize_entities(
        [raw_entity("en", "Greenhorn"), raw_entity("zh-CN", "0")],
        aliases={},
        categories={},
    )

    assert entities[0].name_zh == "0"
    assert entities[0].translation_status == "invalid"


def test_blank_localized_name_is_missing() -> None:
    entities = normalize_entities(
        [raw_entity("en", "Greenhorn"), raw_entity("zh-CN", "  ")],
        aliases={},
        categories={},
    )

    assert entities[0].translation_status == "missing"


def raw_entity(locale: str, name: str) -> RawEntity:
    return RawEntity(
        source="official_game",
        entity_type="achievement",
        source_id="0",
        internal_name=name,
        name=name,
        description=None,
        locale=locale,
        source_file="Data/Achievements.json",
    )
