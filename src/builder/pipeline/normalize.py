from __future__ import annotations

from collections import defaultdict

from builder.models import NormalizedEntity, RawEntity


def normalize_entities(
    raw_entities: list[RawEntity],
    aliases: dict[str, list[str]],
    categories: dict[str, str],
) -> list[NormalizedEntity]:
    grouped: dict[str, list[RawEntity]] = defaultdict(list)
    for entity in raw_entities:
        grouped[build_entity_id(entity)].append(entity)

    normalized: list[NormalizedEntity] = []
    for entity_id, group in sorted(grouped.items()):
        normalized.append(build_normalized_entity(entity_id, group, aliases, categories))
    return normalized


def build_entity_id(entity: RawEntity) -> str:
    source_id = entity.source_id.strip()
    internal_name = (entity.internal_name or "").strip()
    stable = source_id if source_id else internal_name
    stable = stable.replace(" ", "-")
    return f"{entity.entity_type}:{stable}"


def build_normalized_entity(
    entity_id: str,
    group: list[RawEntity],
    aliases: dict[str, list[str]],
    categories: dict[str, str],
) -> NormalizedEntity:
    zh_entity = find_locale(group, "zh-CN")
    en_entity = find_locale(group, "en")
    primary = zh_entity or en_entity or group[0]
    name_zh = pick_value(zh_entity, en_entity, "name")
    description_zh = pick_value(zh_entity, en_entity, "description")
    translation_status = "complete" if zh_entity and zh_entity.name else "missing"
    return NormalizedEntity(
        id=entity_id,
        entity_type=primary.entity_type,
        game_id=primary.source_id,
        internal_name=primary.internal_name,
        name_zh=name_zh or "",
        name_en=pick_value(en_entity, zh_entity, "name"),
        description_zh=description_zh,
        description_en=pick_value(en_entity, zh_entity, "description"),
        category=categories.get(entity_id),
        translation_status=translation_status,
        extra_json=primary.attributes,
        source_file=primary.source_file,
        aliases=aliases.get(entity_id, []),
        keywords=[categories[entity_id]] if entity_id in categories else [],
    )


def find_locale(group: list[RawEntity], locale: str) -> RawEntity | None:
    for entity in group:
        if entity.locale == locale:
            return entity
    return None


def pick_value(
    primary: RawEntity | None,
    fallback: RawEntity | None,
    field_name: str,
) -> str | None:
    if primary is not None:
        value = getattr(primary, field_name)
        if value:
            return value
    if fallback is not None:
        value = getattr(fallback, field_name)
        if value:
            return value
    return None
