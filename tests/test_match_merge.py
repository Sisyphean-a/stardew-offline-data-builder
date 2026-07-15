from __future__ import annotations

from builder.models import MatchResult, NormalizedEntity
from builder.pipeline.match import match_community_entities
from builder.pipeline.merge import merge_official_and_community


def test_match_community_entities_uses_stable_id_and_collects_unmatched() -> None:
    official = [
        NormalizedEntity(
            id="object:24",
            entity_type="object",
            game_id="24",
            internal_name="Parsnip",
            name_zh="防风草",
            name_en="Parsnip",
            description_zh="一种春季块茎。",
            description_en="A spring tuber.",
            category="作物",
            extra_json={},
            source_file="official.json",
        )
    ]
    community = [
        NormalizedEntity(
            id="object:24",
            entity_type="object",
            game_id="24",
            internal_name="Parsnip",
            name_zh="Parsnip",
            name_en="Parsnip",
            description_zh="Community",
            description_en="Community",
            category=None,
            extra_json={"price": 35},
            source_file="community.json",
        ),
        NormalizedEntity(
            id="object:999",
            entity_type="object",
            game_id="999",
            internal_name="GhostTurnip",
            name_zh="Ghost Turnip",
            name_en="Ghost Turnip",
            description_zh="Missing",
            description_en="Missing",
            category=None,
            extra_json={"price": 999},
            source_file="community.json",
        ),
    ]

    matches, unmatched = match_community_entities(official, community, overrides={})

    assert matches["object:24"].matched_by == "stable_id"
    assert len(unmatched) == 1
    assert unmatched[0].source_id == "999"


def test_merge_official_and_community_preserves_official_priority() -> None:
    official = [
        NormalizedEntity(
            id="object:24",
            entity_type="object",
            game_id="24",
            internal_name="Parsnip",
            name_zh="防风草",
            name_en="Parsnip",
            description_zh="一种春季块茎。",
            description_en="A spring tuber.",
            category="作物",
            extra_json={"quality": "official"},
            source_file="official.json",
            aliases=["萝卜"],
            keywords=["作物"],
        )
    ]
    community = [
        NormalizedEntity(
            id="object:24",
            entity_type="object",
            game_id="24",
            internal_name="Parsnip",
            name_zh="Parsnip",
            name_en="Parsnip",
            description_zh="Community",
            description_en="Community",
            category=None,
            extra_json={"price": 35},
            source_file="community.json",
            aliases=["根茎"],
            keywords=["春季"],
        )
    ]
    matches = {
        "object:24": MatchResult(entity_id="object:24", matched_by="stable_id")
    }

    merged = merge_official_and_community(official, community, matches)

    assert merged[0].name_zh == "防风草"
    assert merged[0].extra_json["price"] == 35
    assert merged[0].extra_json["quality"] == "official"
    assert merged[0].aliases == ["萝卜", "根茎"]
