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

        extra_json = merge_extra_json(official_entity, community_match)
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


def merge_extra_json(
    official_entity: NormalizedEntity,
    community_entity: NormalizedEntity,
) -> dict[str, object]:
    extra_json = {
        key: value
        for key, value in community_entity.extra_json.items()
        if key != "_provenance"
    }
    extra_json.update(
        {
            key: value
            for key, value in official_entity.extra_json.items()
            if key != "_provenance"
        }
    )
    provenance = merge_provenance(
        official_entity.extra_json.get("_provenance"),
        community_entity.extra_json.get("_provenance"),
    )
    extra_json["_provenance"] = provenance
    return extra_json


def merge_provenance(
    official: object, community: object
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for value in (official, community):
        if not isinstance(value, dict):
            continue
        for source, files in value.items():
            if isinstance(source, str) and isinstance(files, list):
                merged.setdefault(source, []).extend(str(item) for item in files)
    return {source: list(dict.fromkeys(files)) for source, files in sorted(merged.items())}
