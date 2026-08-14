from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from builder.models import NormalizedEntity, production_attributes, structured_attributes
from builder.pipeline.official_item_index import (
    ItemReferenceResolver,
    add_item_reference,
    add_tag_references,
    build_fish_tag_index,
    build_tag_index,
)
from builder.pipeline.official_shop_references import build_shop_index
from builder.pipeline.official_values import (
    compact,
    dictionary_list,
    parse_bundle_ingredients,
    parse_ingredients,
    simplify_outputs,
    simplify_produced_items,
    string_set,
    unqualified_item_id,
)
from builder.sources.official_support import OfficialSupportData


@dataclass
class OfficialReferenceIndex:
    fish_locations: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    monster_locations: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    fish_ponds: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    machine_uses: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    shop_offers: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    used_in: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: defaultdict(list)
    )


def build_reference_index(
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
    by_id: dict[str, NormalizedEntity],
    *,
    allow_legacy: bool = False,
) -> OfficialReferenceIndex:
    index = OfficialReferenceIndex()
    resolver = ItemReferenceResolver.create(by_id, allow_legacy=allow_legacy)
    build_shop_index(index.shop_offers, support.shops, resolver)
    build_location_index(index.fish_locations, support.locations, by_id)
    build_monster_location_index(index.monster_locations, support.locations, by_id)
    build_pond_index(index.fish_ponds, support.fish_ponds, by_id, allow_legacy=allow_legacy)
    build_machine_index(index.machine_uses, support.machines, resolver, allow_legacy=allow_legacy)
    build_recipe_index(index.used_in, entities, resolver, allow_legacy=allow_legacy)
    return index


def build_location_index(
    index: dict[str, list[dict[str, object]]],
    locations: dict[str, dict[str, Any]],
    by_id: dict[str, NormalizedEntity],
) -> None:
    for location_id, location in locations.items():
        for fish in dictionary_list(location.get("Fish")):
            item_id = unqualified_item_id(fish.get("ItemId"))
            entity_id = f"fish:{item_id}" if item_id else ""
            if entity_id not in by_id:
                continue
            index[entity_id].append(location_reference(location_id, fish))


def build_monster_location_index(
    index: dict[str, list[dict[str, object]]],
    locations: dict[str, dict[str, Any]],
    by_id: dict[str, NormalizedEntity],
) -> None:
    for location_id, location in locations.items():
        for monster in monster_records(location.get("Monsters")):
            entity_id = resolve_monster_entity(monster, by_id)
            if entity_id is None:
                continue
            index[entity_id].append(monster_location_reference(location_id, monster))


def monster_records(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)] + [
            {"Id": item} for item in value if isinstance(item, str) and item.strip()
        ]
    if isinstance(value, dict):
        records: list[dict[str, Any]] = []
        for key, item in value.items():
            if isinstance(item, dict):
                record = dict(item)
                record.setdefault("Id", str(key))
                records.append(record)
            elif isinstance(item, str):
                records.append({"Id": item})
            elif item is True:
                records.append({"Id": str(key)})
        return records
    return []


def resolve_monster_entity(
    record: dict[str, Any],
    by_id: dict[str, NormalizedEntity],
) -> str | None:
    raw_id = next(
        (record.get(key) for key in ("Id", "Name", "MonsterName", "MonsterId", "Type")),
        None,
    )
    if not isinstance(raw_id, str) or not raw_id.strip():
        return None
    value = raw_id.strip()
    if value.startswith("monster:"):
        value = value.split(":", 1)[1]
    normalized = value.replace(" ", "-").casefold()
    matches = [
        entity_id
        for entity_id, entity in by_id.items()
        if entity.entity_type == "monster"
        and (
            entity_id.split(":", 1)[-1].casefold() == normalized
            or (entity.game_id or "").casefold() == value.casefold()
            or (entity.internal_name or "").casefold() == value.casefold()
        )
    ]
    return sorted(matches)[0] if len(matches) == 1 else None


def monster_location_reference(
    location_id: str,
    monster: dict[str, Any],
) -> dict[str, object]:
    return compact(
        {
            "_source": "Data/Locations.json",
            "locationId": location_id,
            "condition": monster.get("Condition"),
            "minDepth": monster.get("MinDepth"),
            "maxDepth": monster.get("MaxDepth"),
            "minTime": monster.get("MinTime"),
            "maxTime": monster.get("MaxTime"),
        }
    )


def location_reference(
    location_id: str,
    fish: dict[str, Any],
) -> dict[str, object]:
    return compact(
        {
            "_source": "Data/Locations.json",
            "locationId": location_id,
            "season": fish.get("Season"),
            "areaId": fish.get("FishAreaId"),
            "chance": fish.get("Chance"),
            "condition": fish.get("Condition"),
            "minFishingLevel": fish.get("MinFishingLevel"),
            "minDistanceFromShore": fish.get("MinDistanceFromShore"),
            "maxDistanceFromShore": fish.get("MaxDistanceFromShore"),
        }
    )


def build_pond_index(
    index: dict[str, list[dict[str, object]]],
    ponds: list[dict[str, Any]],
    by_id: dict[str, NormalizedEntity],
    *,
    allow_legacy: bool = False,
) -> None:
    fish_tags = build_fish_tag_index(by_id, allow_legacy=allow_legacy)
    for pond in ponds:
        required_tags = string_set(pond.get("RequiredTags"))
        for entity_id, tags in fish_tags.items():
            if required_tags and not required_tags.issubset(tags):
                continue
            index[entity_id].append(pond_reference(pond, required_tags))


def pond_reference(
    pond: dict[str, Any],
    required_tags: set[str],
) -> dict[str, object]:
    return compact(
        {
            "_source": "Data/FishPondData.json",
            "ruleId": pond.get("Id"),
            "requiredTags": sorted(required_tags),
            "maxPopulation": pond.get("MaxPopulation"),
            "spawnTime": pond.get("SpawnTime"),
            "producedItems": simplify_produced_items(pond.get("ProducedItems")),
            "populationGates": pond.get("PopulationGates"),
        }
    )


def build_machine_index(
    index: dict[str, list[dict[str, object]]],
    machines: dict[str, dict[str, Any]],
    resolver: ItemReferenceResolver,
    *,
    allow_legacy: bool = False,
) -> None:
    tag_index = build_tag_index(resolver.by_id, allow_legacy=allow_legacy)
    for machine_id, machine in machines.items():
        for rule in dictionary_list(machine.get("OutputRules")):
            for trigger in dictionary_list(rule.get("Triggers")):
                reference = machine_reference(machine_id, rule, trigger)
                add_item_reference(
                    index,
                    trigger.get("RequiredItemId"),
                    reference,
                    resolver=resolver,
                )
                add_tag_references(
                    index,
                    trigger.get("RequiredTags"),
                    reference,
                    tag_index=tag_index,
                    candidate_ids=resolver.machine_entity_ids,
                )


def machine_reference(
    machine_id: str,
    rule: dict[str, Any],
    trigger: dict[str, Any],
) -> dict[str, object]:
    return compact(
        {
            "_source": "Data/Machines.json",
            "machineId": machine_id,
            "ruleId": rule.get("Id"),
            "triggerId": trigger.get("Id"),
            "requiredCount": trigger.get("RequiredCount"),
            "requiredTags": trigger.get("RequiredTags"),
            "condition": trigger.get("Condition"),
            "outputs": simplify_outputs(rule.get("OutputItem")),
            "minutesUntilReady": rule.get("MinutesUntilReady"),
            "daysUntilReady": rule.get("DaysUntilReady"),
        }
    )


def build_recipe_index(
    index: dict[str, list[dict[str, object]]],
    entities: list[NormalizedEntity],
    resolver: ItemReferenceResolver,
    *,
    allow_legacy: bool = False,
) -> None:
    for usage in entities:
        ingredients = usage_ingredients(usage, allow_legacy=allow_legacy)
        if not ingredients:
            continue
        for ingredient in ingredients:
            reference = {
                "_source": usage.source_file,
                "usageId": usage.id,
                "usageType": usage.entity_type,
                "quantity": ingredient["quantity"],
                "quality": ingredient.get("quality"),
            }
            add_item_reference(
                index,
                ingredient["itemId"],
                reference,
                resolver=resolver,
            )


def usage_ingredients(
    entity: NormalizedEntity,
    *,
    allow_legacy: bool = False,
) -> list[dict[str, object]] | None:
    attributes = structured_attributes(entity) if allow_legacy else production_attributes(entity)
    if entity.entity_type in {"cooking_recipe", "crafting_recipe"}:
        ingredients = attributes.get("Ingredients")
        if isinstance(ingredients, list):
            return [item for item in ingredients if isinstance(item, dict)]
        if isinstance(ingredients, str):
            return parse_ingredients(ingredients)
    if entity.entity_type == "bundle":
        ingredients = attributes.get("BundleIngredients")
        if isinstance(ingredients, list):
            return [item for item in ingredients if isinstance(item, dict)]
        if isinstance(ingredients, str):
            return parse_bundle_ingredients(ingredients)
    if not allow_legacy:
        return None
    # Legacy-only callers are kept for the explicit v4/reference compatibility path.
    fields = attributes.get("legacyFields")
    if not isinstance(fields, list):
        return None
    if entity.entity_type in {"cooking_recipe", "crafting_recipe"}:
        return parse_ingredients(fields[0] if fields else None)
    if entity.entity_type == "bundle":
        return parse_bundle_ingredients(fields[2] if len(fields) > 2 else None)
    return None
