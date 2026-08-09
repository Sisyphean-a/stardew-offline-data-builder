from __future__ import annotations

import re
from collections import defaultdict

from builder.models import NormalizedEntity, RawEntity
from builder.pipeline.normalize_images import (
    IMAGE_METADATA_KEYS,
    copy_avatar_metadata,
    inherit_harvest_item_image,
)
from builder.pipeline.normalize_schedule import (
    SCHEDULE_PHRASES,
    display_villager_name,
    friendly_schedule_key,
    referenced_villager,
    resolve_schedule_title,
    translate_schedule_parts,
)
from builder.pipeline.normalize_support import (
    displayable_entity_name,
    drop_record_id,
    entity_type_label,
    humanize_identifier,
    item_key,
    item_key_value,
    reference_key,
    technical_name,
    villager_key,
)
from builder.pipeline.normalize_titles import (
    apply_contextual_display_data,
    fallback_name,
    ginger_event_name,
    ginger_island_title,
    labelled_identifier,
    resolve_drop_title,
    resolve_gift_title,
    shop_title,
    tailoring_fallback_identifier,
    tailoring_source_title,
    tailoring_title,
)

__all__ = [
    "IMAGE_METADATA_KEYS",
    "NON_LOCALIZABLE_ENTITY_TYPES",
    "NON_LOCALIZABLE_NAMES",
    "apply_contextual_display_data",
    "build_entity_id",
    "build_normalized_entity",
    "build_provenance",
    "copy_avatar_metadata",
    "display_villager_name",
    "displayable_entity_name",
    "drop_record_id",
    "entity_type_label",
    "fallback_name",
    "friendly_schedule_key",
    "ginger_event_name",
    "ginger_island_title",
    "humanize_identifier",
    "inherit_harvest_item_image",
    "is_displayable_translation",
    "item_key",
    "item_key_value",
    "labelled_identifier",
    "normalize_entities",
    "reference_key",
    "referenced_villager",
    "resolve_drop_title",
    "resolve_gift_title",
    "resolve_schedule_title",
    "SCHEDULE_PHRASES",
    "shop_title",
    "tailoring_fallback_identifier",
    "tailoring_source_title",
    "tailoring_title",
    "technical_name",
    "translate_schedule_parts",
    "villager_key",
]

NON_LOCALIZABLE_ENTITY_TYPES = frozenset(
    {
        "drop",
        "ginger_island",
        "npc_schedule",
        "shop",
        "tailoring_recipe",
        "villager_gift",
    }
)
NON_LOCALIZABLE_NAMES = frozenset({"???"})


def normalize_entities(
    raw_entities: list[RawEntity],
    aliases: dict[str, list[str]],
    categories: dict[str, str],
) -> list[NormalizedEntity]:
    grouped: dict[str, list[RawEntity]] = defaultdict(list)
    for entity in raw_entities:
        grouped[build_entity_id(entity)].append(entity)
    normalized = [
        build_normalized_entity(entity_id, group, aliases, categories)
        for entity_id, group in sorted(grouped.items())
    ]
    villagers = {
        villager_key(entity): entity
        for entity in normalized
        if entity.entity_type == "villager"
    }
    items = build_item_index(normalized)
    monsters = {
        villager_key(entity): entity
        for entity in normalized
        if entity.entity_type == "monster"
    }
    return [
        apply_contextual_display_data(entity, villagers, items, monsters)
        for entity in normalized
    ]


def build_item_index(entities: list[NormalizedEntity]) -> dict[str, NormalizedEntity]:
    items: dict[str, NormalizedEntity] = {}
    item_types = {"mineral", "ring", "big_craftable", "footwear", "weapon", "tool", "trinket"}
    for entity in entities:
        if entity.entity_type == "object":
            items[item_key(entity)] = entity
    for entity in entities:
        if entity.entity_type in item_types:
            items.setdefault(item_key(entity), entity)
    return items


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
    chinese_name = pick_group_value(chinese, [], "name")
    name_zh = fallback_name(primary, chinese_name or pick_group_value(english, [], "name"))
    extra_json = dict(primary.attributes)
    extra_json["_provenance"] = build_provenance(group)
    return NormalizedEntity(
        id=entity_id,
        entity_type=primary.entity_type,
        game_id=primary.source_id,
        internal_name=first_nonempty(group, "internal_name"),
        name_zh=name_zh or "",
        name_en=pick_group_value(english, chinese, "name"),
        description_zh=pick_group_value(chinese, english, "description"),
        description_en=pick_group_value(english, chinese, "description"),
        category=categories.get(entity_id),
        translation_status=translation_status(primary, chinese_name),
        extra_json=extra_json,
        source_file=primary.source_file,
        aliases=aliases.get(entity_id, []),
        keywords=[categories[entity_id]] if entity_id in categories else [],
    )


def translation_status(primary: RawEntity, chinese_name: str | None) -> str:
    if not requires_translation(primary):
        return "not_applicable"
    if not chinese_name or not chinese_name.strip():
        return "missing"
    return "complete" if is_displayable_translation(chinese_name) else "invalid"


def is_displayable_translation(name: str) -> bool:
    return not bool(re.fullmatch(r"\d+", name.strip()))


def requires_translation(entity: RawEntity) -> bool:
    if entity.attributes.get("translationRequired") is False:
        return False
    if entity.entity_type in NON_LOCALIZABLE_ENTITY_TYPES:
        return False
    return entity.name not in NON_LOCALIZABLE_NAMES


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
    provenance: dict[str, list[str]] = defaultdict(list)
    for entity in group:
        provenance[entity.source].append(entity.source_file)
    return {source: sorted(set(files)) for source, files in sorted(provenance.items())}
