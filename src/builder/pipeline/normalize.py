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
    return [
        build_normalized_entity(entity_id, group, aliases, categories)
        for entity_id, group in sorted(grouped.items())
    ]


def build_entity_id(entity: RawEntity) -> str:
    stable = entity.source_id.strip() or (entity.internal_name or "").strip()
    return f"{entity.entity_type}:{stable.replace(' ', '-')}"


def build_normalized_entity(
    entity_id: str,
    group: list[RawEntity],
    aliases: dict[str, list[str]],
    categories: dict[str, str],
) -> NormalizedEntity:
    english = locale_entities(group, "en")
    chinese = locale_entities(group, "zh-CN")
    primary = select_primary(group)
    name_zh = pick_group_value(chinese, english, "name")
    description_zh = pick_group_value(chinese, english, "description")
    extra_json = dict(primary.attributes)
    extra_json["_provenance"] = build_provenance(group)
    return NormalizedEntity(
        id=entity_id,
        entity_type=primary.entity_type,
        game_id=primary.source_id,
        internal_name=first_nonempty(group, "internal_name"),
        name_zh=name_zh or "",
        name_en=pick_group_value(english, chinese, "name"),
        description_zh=description_zh,
        description_en=pick_group_value(english, chinese, "description"),
        category=categories.get(entity_id),
        translation_status="complete" if pick_group_value(chinese, [], "name") else "missing",
        extra_json=extra_json,
        source_file=primary.source_file,
        aliases=aliases.get(entity_id, []),
        keywords=[categories[entity_id]] if entity_id in categories else [],
    )


def locale_entities(group: list[RawEntity], locale: str) -> list[RawEntity]:
    return [entity for entity in group if entity.locale == locale]


def select_primary(group: list[RawEntity]) -> RawEntity:
    return max(
        group,
        key=lambda entity: (len(entity.attributes), entity.locale == "en", entity.source_file),
    )


def first_nonempty(group: list[RawEntity], field_name: str) -> str | None:
    for entity in sorted(group, key=lambda item: item.source_file):
        value = getattr(entity, field_name)
        if value:
            return value
    return None


def pick_group_value(
    primary: list[RawEntity], fallback: list[RawEntity], field_name: str
) -> str | None:
    for entity in [*ranked_entities(primary), *ranked_entities(fallback)]:
        value = getattr(entity, field_name)
        if value:
            return value
    return None


def ranked_entities(entities: list[RawEntity]) -> list[RawEntity]:
    return sorted(entities, key=lambda entity: (-len(entity.attributes), entity.source_file))


def build_provenance(group: list[RawEntity]) -> dict[str, list[str]]:
    provenance: dict[str, list[str]] = {}
    for entity in group:
        provenance.setdefault(entity.source, []).append(entity.source_file)
    return {
        source: sorted(set(files))
        for source, files in sorted(provenance.items())
    }
