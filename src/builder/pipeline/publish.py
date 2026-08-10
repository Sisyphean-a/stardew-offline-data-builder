from __future__ import annotations

from builder.models import NormalizedEntity
from builder.pipeline.official_item_index import ItemReferenceResolver


def filter_publishable_entities(entities: list[NormalizedEntity]) -> list[NormalizedEntity]:
    """Remove entities that have no user-visible content after normalization context is complete."""
    resolver = ItemReferenceResolver.create({entity.id: entity for entity in entities})
    return [
        entity
        for entity in entities
        if not is_non_social_villager(entity) and not is_empty_shop(entity, resolver)
    ]


def is_non_social_villager(entity: NormalizedEntity) -> bool:
    return entity.entity_type == "villager" and is_explicit_false(
        entity.extra_json.get("CanSocialize")
    )


def is_explicit_false(value: object) -> bool:
    return value is False or (
        isinstance(value, str) and value.strip().casefold() == "false"
    )


def is_empty_shop(entity: NormalizedEntity, resolver: ItemReferenceResolver) -> bool:
    if entity.entity_type != "shop":
        return False
    options = entity.extra_json.get("Items")
    return not isinstance(options, list) or not any(
        is_shop_option(option, resolver) for option in options
    )


def is_shop_option(value: object, resolver: ItemReferenceResolver) -> bool:
    if not isinstance(value, dict) or not str(value.get("Id") or "").strip():
        return False
    references: list[object] = [value.get("ItemId"), value.get("TradeItemId")]
    random_ids = value.get("RandomItemId")
    references.extend(random_ids if isinstance(random_ids, list) else [random_ids])
    return any(
        resolver.resolve(reference)
        for reference in references
        if str(reference or "").strip()
    )
