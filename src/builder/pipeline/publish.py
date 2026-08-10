from __future__ import annotations

from builder.models import NormalizedEntity


def filter_publishable_entities(entities: list[NormalizedEntity]) -> list[NormalizedEntity]:
    """Remove explicitly non-social villagers after normalization context is complete."""
    return [entity for entity in entities if not is_non_social_villager(entity)]


def is_non_social_villager(entity: NormalizedEntity) -> bool:
    return entity.entity_type == "villager" and is_explicit_false(
        entity.extra_json.get("CanSocialize")
    )


def is_explicit_false(value: object) -> bool:
    return value is False or (
        isinstance(value, str) and value.strip().casefold() == "false"
    )
