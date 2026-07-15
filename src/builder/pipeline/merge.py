from __future__ import annotations

from builder.models import MatchResult, NormalizedEntity


def merge_official_and_community(
    official_entities: list[NormalizedEntity],
    community_entities: list[NormalizedEntity],
    matches: dict[str, MatchResult],
) -> list[NormalizedEntity]:
    community_by_id = {entity.id: entity for entity in community_entities}
    merged: list[NormalizedEntity] = []

    for official_entity in official_entities:
        community_match = find_matching_community_entity(
            official_entity.id,
            matches,
            community_by_id,
        )
        if community_match is None:
            merged.append(official_entity)
            continue

        extra_json = dict(community_match.extra_json)
        extra_json.update(official_entity.extra_json)
        aliases = unique_items([*official_entity.aliases, *community_match.aliases])
        keywords = unique_items([*official_entity.keywords, *community_match.keywords])
        merged.append(
            official_entity.model_copy(
                update={
                    "extra_json": extra_json,
                    "aliases": aliases,
                    "keywords": keywords,
                }
            )
        )

    return merged


def find_matching_community_entity(
    official_id: str,
    matches: dict[str, MatchResult],
    community_by_id: dict[str, NormalizedEntity],
) -> NormalizedEntity | None:
    for community_id, match in matches.items():
        if match.entity_id == official_id and community_id in community_by_id:
            return community_by_id[community_id]
    return None


def unique_items(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
