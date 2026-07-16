from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from builder.models import NormalizedEntity
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
) -> OfficialReferenceIndex:
    index = OfficialReferenceIndex()
    resolver = ItemReferenceResolver.create(by_id)
    build_shop_index(index.shop_offers, support.shops, resolver)
    build_location_index(index.fish_locations, support.locations, by_id)
    build_pond_index(index.fish_ponds, support.fish_ponds, by_id)
    build_machine_index(index.machine_uses, support.machines, resolver)
    build_recipe_index(index.used_in, entities, resolver)
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
) -> None:
    fish_tags = build_fish_tag_index(by_id)
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
) -> None:
    tag_index = build_tag_index(resolver.by_id)
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
) -> None:
    for usage in entities:
        ingredients = usage_ingredients(usage)
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
) -> list[dict[str, object]] | None:
    fields = entity.extra_json.get("legacyFields")
    if not isinstance(fields, list):
        return None
    if entity.entity_type in {"cooking_recipe", "crafting_recipe"}:
        return parse_ingredients(fields[0] if fields else None)
    if entity.entity_type == "bundle":
        return parse_bundle_ingredients(fields[2] if len(fields) > 2 else None)
    return None
