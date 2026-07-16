from __future__ import annotations

from typing import Any

from builder.models import NormalizedEntity
from builder.pipeline.official_references import (
    OfficialReferenceIndex,
    build_reference_index,
)
from builder.pipeline.official_values import (
    compact,
    integer_at,
    integer_list,
    integer_list_at,
    lower_text,
    lower_text_list,
    parse_ingredients,
    split_words_at,
    text,
    text_at,
)
from builder.sources.official_support import OfficialSupportData


def enrich_official_entities(
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
) -> list[NormalizedEntity]:
    by_id = {entity.id: entity for entity in entities}
    references = build_reference_index(entities, support, by_id)
    return [enrich_entity(entity, references) for entity in entities]


def enrich_entity(
    entity: NormalizedEntity,
    references: OfficialReferenceIndex,
) -> NormalizedEntity:
    derived = derive_entity_fields(entity)
    sources: set[str] = set()
    add_references(derived, "shopOffers", references.shop_offers.get(entity.id), sources)
    add_references(derived, "machineUses", references.machine_uses.get(entity.id), sources)
    add_references(derived, "usedIn", references.used_in.get(entity.id), sources)
    add_type_references(entity, derived, references, sources)
    if not derived:
        return entity
    extra_json = {**entity.extra_json, "officialDerived": derived}
    extra_json["_provenance"] = add_official_provenance(
        entity.extra_json.get("_provenance"), sources
    )
    return entity.model_copy(update={"extra_json": extra_json})


def add_type_references(
    entity: NormalizedEntity,
    derived: dict[str, object],
    references: OfficialReferenceIndex,
    sources: set[str],
) -> None:
    if entity.entity_type == "crop":
        seed_id = str(derived.get("seedItemId", ""))
        add_references(
            derived,
            "seedShopOffers",
            references.shop_offers.get(f"object:{seed_id}"),
            sources,
        )
    if entity.entity_type == "fish":
        add_references(
            derived, "locations", references.fish_locations.get(entity.id), sources
        )
        add_references(
            derived, "fishPondRules", references.fish_ponds.get(entity.id), sources
        )


def add_references(
    derived: dict[str, object],
    key: str,
    values: list[dict[str, object]] | None,
    sources: set[str],
) -> None:
    if not values:
        return
    derived[key] = values
    sources.update(str(value["_source"]) for value in values)


def derive_entity_fields(entity: NormalizedEntity) -> dict[str, object]:
    if entity.entity_type == "crop":
        return derive_crop_fields(entity.extra_json)
    if entity.entity_type == "fish":
        return derive_fish_fields(entity.extra_json)
    if entity.entity_type == "villager":
        return derive_villager_fields(entity.extra_json)
    if entity.entity_type in {"cooking_recipe", "crafting_recipe"}:
        return derive_recipe_fields(entity.extra_json)
    if entity.entity_type in {"object", "mineral", "ring"}:
        return derive_object_fields(entity.extra_json)
    return {}


def derive_crop_fields(data: dict[str, Any]) -> dict[str, object]:
    phases = integer_list(data.get("DaysInPhase"))
    regrow_days = data.get("RegrowDays")
    normalized_regrow = (
        regrow_days
        if isinstance(regrow_days, int) and regrow_days >= 0
        else None
    )
    return compact(
        {
            "seedItemId": text(data.get("SeedItemId")),
            "seasons": lower_text_list(data.get("Seasons")),
            "growDays": sum(phases) if phases else None,
            "growthPhases": phases or None,
            "regrowDays": normalized_regrow,
            "needsWatering": data.get("NeedsWatering"),
            "isPaddyCrop": data.get("IsPaddyCrop"),
            "isTrellisCrop": data.get("IsRaised"),
            "harvestItemId": text(data.get("HarvestItemId")),
            "harvestMin": data.get("HarvestMinStack"),
            "harvestMax": data.get("HarvestMaxStack"),
        }
    )


def derive_fish_fields(data: dict[str, Any]) -> dict[str, object]:
    fields = data.get("legacyFields")
    if not isinstance(fields, list):
        return {}
    return compact(
        {
            "difficulty": integer_at(fields, 1),
            "behavior": text_at(fields, 2),
            "minSize": integer_at(fields, 3),
            "maxSize": integer_at(fields, 4),
            "timeWindows": integer_list_at(fields, 5),
            "seasons": split_words_at(fields, 6),
            "weather": text_at(fields, 7),
        }
    )


def derive_villager_fields(data: dict[str, Any]) -> dict[str, object]:
    return compact(
        {
            "birthday": compact(
                {
                    "season": lower_text(data.get("BirthSeason")),
                    "day": data.get("BirthDay"),
                }
            ),
            "homeRegion": data.get("HomeRegion"),
            "gender": data.get("Gender"),
            "canBeRomanced": data.get("CanBeRomanced"),
            "loveInterest": data.get("LoveInterest"),
        }
    )


def derive_recipe_fields(data: dict[str, Any]) -> dict[str, object]:
    fields = data.get("legacyFields")
    ingredient_source = fields[0] if isinstance(fields, list) and fields else None
    return compact(
        {
            "ingredients": parse_ingredients(ingredient_source),
            "outputItemId": text(data.get("outputItemId")),
            "outputEntityType": text(data.get("outputEntityType")),
        }
    )


def derive_object_fields(data: dict[str, Any]) -> dict[str, object]:
    return compact(
        {
            "sellPrice": data.get("Price"),
            "edibility": data.get("Edibility"),
            "contextTags": data.get("ContextTags"),
        }
    )


def add_official_provenance(
    value: object,
    sources: set[str],
) -> dict[str, list[str]]:
    provenance: dict[str, list[str]] = {}
    if isinstance(value, dict):
        provenance = {
            str(source): [str(path) for path in paths]
            for source, paths in value.items()
            if isinstance(paths, list)
        }
    official = [*provenance.get("official", []), *sources]
    provenance["official"] = sorted(set(official))
    return provenance
