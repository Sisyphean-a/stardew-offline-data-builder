from __future__ import annotations

from builder.models import MatchResult, NormalizedEntity, UnmatchedRecord


def match_community_entities(
    official_entities: list[NormalizedEntity],
    community_entities: list[NormalizedEntity],
    overrides: dict[str, str],
) -> tuple[dict[str, MatchResult], list[UnmatchedRecord]]:
    by_id = {entity.id: entity for entity in official_entities}
    by_internal_name = {
        normalize_key(entity.internal_name): entity.id
        for entity in official_entities
        if entity.internal_name
    }
    by_english_name = {
        normalize_key(entity.name_en): entity.id
        for entity in official_entities
        if entity.name_en
    }

    matches: dict[str, MatchResult] = {}
    unmatched: list[UnmatchedRecord] = []
    for entity in community_entities:
        if entity.id in by_id:
            matches[entity.id] = MatchResult(entity_id=entity.id, matched_by="stable_id")
            continue

        normalized_internal_name = normalize_key(entity.internal_name)
        if normalized_internal_name and normalized_internal_name in by_internal_name:
            entity_id = by_internal_name[normalized_internal_name]
            matches[entity.id] = MatchResult(entity_id=entity_id, matched_by="internal_name")
            continue

        normalized_english_name = normalize_key(entity.name_en)
        if normalized_english_name and normalized_english_name in by_english_name:
            entity_id = by_english_name[normalized_english_name]
            matches[entity.id] = MatchResult(entity_id=entity_id, matched_by="name_en")
            continue

        if entity.id in overrides:
            matches[entity.id] = MatchResult(entity_id=overrides[entity.id], matched_by="override")
            continue

        unmatched.append(
            UnmatchedRecord(
                source="community",
                entity_type=entity.entity_type,
                source_id=entity.game_id or entity.id,
                name=entity.name_en,
                attempted=["stable_id", "internal_name", "name_en", "override"],
                reason="未找到可接受的稳定匹配",
            )
        )

    return matches, unmatched


def normalize_key(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().lower().replace(" ", "").replace("-", "")
