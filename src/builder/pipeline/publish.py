from __future__ import annotations

from builder.models import NormalizedEntity, production_attributes, structured_attributes
from builder.pipeline.official_item_index import ItemReferenceResolver


def filter_publishable_entities(
    entities: list[NormalizedEntity],
    *,
    allow_legacy: bool = False,
) -> list[NormalizedEntity]:
    """Remove entities with no visible content at the selected input boundary."""
    resolver = ItemReferenceResolver.create(
        {entity.id: entity for entity in entities},
        allow_legacy=allow_legacy,
    )
    return [
        entity
        for entity in entities
        if not is_non_social_villager(entity, allow_legacy=allow_legacy)
        and not is_empty_shop(entity, resolver, allow_legacy=allow_legacy)
    ]


def attributes_for(entity: NormalizedEntity, *, allow_legacy: bool) -> dict[str, object]:
    return structured_attributes(entity) if allow_legacy else production_attributes(entity)


def is_non_social_villager(entity: NormalizedEntity, *, allow_legacy: bool = False) -> bool:
    return entity.entity_type == "villager" and is_explicit_false(
        attributes_for(entity, allow_legacy=allow_legacy).get("CanSocialize")
    )


def is_explicit_false(value: object) -> bool:
    return value is False or (
        isinstance(value, str) and value.strip().casefold() == "false"
    )


def is_empty_shop(
    entity: NormalizedEntity,
    resolver: ItemReferenceResolver,
    *,
    allow_legacy: bool = False,
) -> bool:
    if entity.entity_type != "shop":
        return False
    options = attributes_for(entity, allow_legacy=allow_legacy).get("Items")
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
