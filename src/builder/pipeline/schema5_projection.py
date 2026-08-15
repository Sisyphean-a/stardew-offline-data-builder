from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

from builder.models import NormalizedEntity, production_attributes
from builder.models_schema5 import (
    Schema5ClaimEvidence,
    Schema5ConditionSet,
    Schema5ConditionTerm,
    Schema5Entity,
    Schema5EntityCard,
    Schema5Evidence,
    Schema5Facet,
    Schema5FacetGroup,
    Schema5FactItem,
    Schema5FactSlot,
    Schema5Package,
    Schema5Relation,
    Schema5RelationGroup,
    Schema5SourceDocument,
    Schema5SourceLocator,
    Schema5Visual,
)
from builder.pipeline.official_item_index import ItemReferenceResolver
from builder.pipeline.official_references import build_reference_index
from builder.pipeline.official_shop_references import build_shop_index
from builder.pipeline.official_values import entity_ids_for_item, parse_ingredients
from builder.sources.official_support import OfficialSupportData
from builder.utils.hashing import sha256_file

# Every schema-5 projection read goes through the structured channel.  The
# staging wrapper materializes a fixture-only copy before entering this path.
structured_attributes = production_attributes

RELATION_FAMILIES = {"kinship", "friendship", "love_interest"}

# These tables mirror the item branches in the official game code.  They are
# deliberately separate from Weapons.json's MineBaseLevel/MineMinLevel fields:
# those fields are not, on their own, a player-facing acquisition location.
MINE_SPECIAL_WEAPON_RULES: dict[str, tuple[tuple[int, int | None], ...]] = {
    "16": ((1, 19),),
    "24": ((1, 19),),
    "22": ((20, 39),),
    "15": ((20, 59),),
    "6": ((40, 59),),
    "26": ((40, 79),),
    "27": ((40, 79),),
    "19": ((60, 79), (100, 119)),
    "48": ((80, 99),),
    "18": ((80, None),),
    "28": ((80, 99), (120, None)),
    "52": ((80, 99), (120, None)),
    "3": ((80, 99), (120, None)),
    "46": ((100, 119),),
    "45": ((120, None),),
    "50": ((100, None),),
}
MINE_STANDARD_CHEST_WEAPONS = {"11": 20, "32": 40, "21": 60, "8": 90}
MINE_REMIXED_CHEST_WEAPONS: dict[str, tuple[int, ...]] = {
    "12": (10,),
    "17": (10,),
    "22": (10,),
    "31": (10,),
    "11": (20,),
    "24": (20,),
    "20": (20,),
    "1": (50,),
    "43": (50,),
    "21": (60,),
    "44": (60,),
    "6": (60,),
    "18": (60,),
    "27": (60,),
    "10": (80,),
    "7": (80,),
    "46": (80,),
    "19": (80,),
    "8": (90,),
    "52": (90,),
    "45": (90,),
    "5": (90,),
    "60": (90,),
    "50": (110,),
    "28": (110,),
}
VOLCANO_CHEST_WEAPONS: dict[str, int] = {
    "54": 0,
    "55": 0,
    "56": 0,
    "57": 1,
    "58": 1,
    "59": 1,
}
# Single-item rules whose acquisition is implemented outside the ordinary
# shop/chest tables.  The source method is kept explicit so an App consumer
# can distinguish a game rule from a direct JSON row.
SPECIAL_WEAPON_ACQUISITION_RULES: dict[str, tuple[str, str, str]] = {
    "4": (
        "沙漠三柱规则奖励",
        "GameLocation.getGalaxySword",
        "official-galaxy-sword-rule-to-weapon-acquisition-v1",
    ),
    "47": (
        "开局工具",
        "Farmer.initialTools",
        "official-initial-tools-to-weapon-acquisition-v1",
    ),
    "53": (
        "采石场矿井尽头",
        "GameLocation.performAction:GoldenScythe",
        "official-golden-scythe-action-to-weapon-acquisition-v1",
    ),
    "62": (
        "火山锻造：银河剑 + 3 个银河之魂",
        "Tool.Forge",
        "official-infinity-forge-to-weapon-acquisition-v1",
    ),
    "63": (
        "火山锻造：银河之锤 + 3 个银河之魂",
        "Tool.Forge",
        "official-infinity-forge-to-weapon-acquisition-v1",
    ),
    "64": (
        "火山锻造：银河匕首 + 3 个银河之魂",
        "Tool.Forge",
        "official-infinity-forge-to-weapon-acquisition-v1",
    ),
    "61": (
        "挑战矿井额外难度奖励",
        "MineShaft.getSpecialItemForThisMineLevel",
        "official-mine-challenge-item-to-weapon-acquisition-v1",
    ),
    "66": (
        "耕种精通奖励",
        "MasteryTrackerMenu",
        "official-mastery-reward-to-weapon-acquisition-v1",
    ),
}
KINSHIP_LABELS = {
    "relative_aunt": "姨母/姑母",
    "relative_brother": "兄弟",
    "relative_child": "子女",
    "relative_daughter": "女儿",
    "relative_father": "父亲",
    "relative_granddaughter": "孙女",
    "relative_grandfather": "祖父",
    "relative_grandmother": "祖母",
    "relative_grandson": "孙子",
    "relative_mother": "母亲",
    "relative_mom": "母亲",
    "relative_dad": "父亲",
    "relative_grandpa": "祖父",
    "relative_grandma": "祖母",
    "relative_nephew": "侄子/外甥",
    "relative_niece": "侄女/外甥女",
    "relative_sister": "姐妹",
    "relative_son": "儿子",
    "relative_uncle": "叔伯/舅父",
    "relative_wife": "妻子",
    "relative_husband": "丈夫",
}


def build_schema5_package(
    entities: list[NormalizedEntity],
    output_dir: Path,
    *,
    game_version: str,
    support: OfficialSupportData | None = None,
    support_entities: list[NormalizedEntity] | None = None,
) -> Schema5Package:
    """Project normalized official input into an isolated typed schema-5 package.

    This production projection intentionally does not read ``officialDerived``.
    It projects stable entity fields, direct villager relationship records,
    typed category facts, support references, and materialized visual files.
    The formal release gate adds explicit not-collected rows for unanswered
    registered player questions instead of silently omitting them.
    """
    entity_ids = {entity.id for entity in entities}
    by_id = {entity.id: entity for entity in entities}
    schema_entities = [to_schema_entity(entity) for entity in entities]
    package = Schema5Package(
        entities=schema_entities,
        entity_cards=[to_card(entity) for entity in entities],
    )
    source_documents: dict[str, Schema5SourceDocument] = {}
    source_locators: dict[str, Schema5SourceLocator] = {}
    locators_by_entity: dict[str, str] = {}
    for entity in entities:
        document, locator = source_for_entity(entity, game_version)
        source_documents[document.id] = document
        source_locators[locator.id] = locator
        locators_by_entity[entity.id] = locator.id
        if entity.entity_type == "crop":
            package.evidence.append(
                Schema5Evidence(
                    id=f"evidence:{entity.id}:crop-fields",
                    source_locator_id=locator.id,
                    evidence_kind="direct",
                )
            )
        package.claim_evidence.append(
            direct_claim(entity.id, "card", locator.id, package)
        )
        visual_rows = visuals_for_entity(entity, output_dir, entity_ids)
        package.visuals.extend(visual_rows)
        for visual in visual_rows:
            package.claim_evidence.append(
                visual_claim(visual.id, locator.id, package)
            )
        fact_slots = typed_facts(entity, by_id=by_id)
        fact_slots.extend(recipe_output_facts(entity, by_id))
        package.fact_slots.extend(fact_slots)
        for fact in fact_slots:
            source_entity_id = fact_source_entity_id(entity, fact, by_id)
            fact_locator_id = source_locators_by_entity(
                source_entity_id, locators_by_entity, locator.id
            )
            package.claim_evidence.append(
                fact_claim(
                    fact,
                    fact_locator_id,
                    package,
                    input_claim_id=source_entity_id if source_entity_id != entity.id else None,
                )
            )
            if entity.entity_type == "crop" and fact.slot_key == "seasons":
                add_crop_season_facets(
                    package,
                    entity.id,
                    structured_attributes(entity).get("Seasons"),
                    fact.id,
                    fact_locator_id,
                )
        add_recipe_material_facts(package, entity, by_id, locator.id)

    add_recipe_output_material_facts(package, entities, by_id, locators_by_entity)
    add_drop_projections(package, entities, by_id, locators_by_entity)
    add_inline_drop_projections(package, entities, by_id, locators_by_entity)
    relation_rows = relations_for_entities(entities, entity_ids)
    package.relation_groups.extend(group for group, _ in relation_rows)
    for group, relations in relation_rows:
        package.claim_evidence.append(
            direct_claim(
                group.id,
                "relation_group",
                locators_by_entity[group.entity_id],
                package,
            )
        )
        package.relations.extend(relations)
        for relation in relations:
            package.claim_evidence.append(
                relation_claim(
                    relation,
                    locators_by_entity[group.entity_id],
                    package,
                )
            )
    package.source_documents = sorted(source_documents.values(), key=lambda item: item.id)
    package.source_locators = sorted(source_locators.values(), key=lambda item: item.id)
    if support is not None:
        add_typed_support_projections(
            package, entities, support, entity_ids, game_version, locators_by_entity
        )
    if support_entities:
        add_villager_support_projections(package, support_entities, by_id, game_version)
    project_card_actions(package)
    return package


def project_card_actions(package: Schema5Package) -> None:
    """Derive the two list-level action answers from typed fact rows."""
    slots_by_entity: dict[str, list[Schema5FactSlot]] = defaultdict(list)
    for slot in package.fact_slots:
        slots_by_entity[slot.entity_id].append(slot)
    items_by_slot: dict[str, list[Schema5FactItem]] = defaultdict(list)
    for item in package.fact_items:
        items_by_slot[item.slot_id].append(item)
    updated = []
    for card in package.entity_cards:
        actions: list[str] = []
        for slot in sorted(slots_by_entity.get(card.entity_id, []), key=lambda item: item.slot_key):
            if slot.status not in {"fixed", "conditional", "dynamic_rule"}:
                continue
            if slot.slot_key in {"sell_price", "purchase_price", "seed_purchase_price"}:
                value = slot.integer_value
                if value is not None:
                    label = {
                        "sell_price": "售价",
                        "purchase_price": "购买价",
                        "seed_purchase_price": "种子价",
                    }[slot.slot_key]
                    actions.append(f"{label}：{value}")
            elif slot.slot_key == "seasons" and slot.text_value:
                actions.append(f"季节：{slot.text_value}")
            elif slot.slot_key == "fishing_locations":
                values = [
                    item.text_value
                    for item in items_by_slot.get(slot.id, [])
                    if item.text_value
                ]
                if values:
                    actions.append(f"地点：{'、'.join(values[:3])}")
            if len(actions) == 2:
                break
        updated.append(
            replace(
                card,
                action_summary_1=actions[0] if actions else card.action_summary_1,
                action_summary_2=actions[1] if len(actions) > 1 else card.action_summary_2,
            )
        )
    package.entity_cards = updated


def build_schema5_staging_package(
    entities: list[NormalizedEntity],
    output_dir: Path,
    *,
    game_version: str,
    support: OfficialSupportData | None = None,
    support_entities: list[NormalizedEntity] | None = None,
) -> Schema5Package:
    """Compatibility entrypoint for explicitly non-publishable staging.

    Staging fixtures may still be authored with the v4-shaped test model.  Copy
    that input into the structured channel before calling the same strict
    projection; the formal candidate never takes this compatibility branch.
    """
    staged_entities = [
        entity
        if entity.source_attributes
        else entity.model_copy(update={"source_attributes": _fixture_attributes(entity)})
        for entity in entities
    ]
    staged_support_entities = [
        support_entity
        if support_entity.source_attributes
        else support_entity.model_copy(
            update={"source_attributes": _fixture_attributes(support_entity)}
        )
        for support_entity in (support_entities or [])
    ]
    return build_schema5_package(
        staged_entities,
        output_dir,
        game_version=game_version,
        support=support,
        support_entities=staged_support_entities,
    )


def add_villager_support_projections(
    package: Schema5Package,
    support_entities: list[NormalizedEntity],
    by_id: dict[str, NormalizedEntity],
    game_version: str,
) -> None:
    """Aggregate schedule and gift records into typed villager facts."""
    documents = {document.id: document for document in package.source_documents}
    locators = {locator.id: locator for locator in package.source_locators}
    for support_entity in support_entities:
        owner_id = support_entity.game_id.split(":", 1)[0] if support_entity.game_id else ""
        villager_id = f"villager:{owner_id}"
        if villager_id not in by_id:
            continue
        locator_id = f"locator:support:{stable_part(support_entity.id)}"
        document_digest = hashlib.sha256(
            support_entity.source_file.encode()
        ).hexdigest()[:16]
        document_id = f"source:support:{document_digest}"
        documents.setdefault(
            document_id,
            Schema5SourceDocument(
                id=document_id,
                source_kind="official_direct",
                title=support_entity.source_file.replace("\\", "/"),
                game_version=game_version,
            ),
        )
        locators.setdefault(
            locator_id,
            Schema5SourceLocator(
                id=locator_id,
                source_document_id=document_id,
                source_file=support_entity.source_file.replace("\\", "/"),
                record_key=support_entity.game_id or support_entity.id,
            ),
        )
        attributes = structured_attributes(support_entity)
        if support_entity.entity_type == "npc_schedule":
            text = schedule_fact_text(attributes)
            if text:
                add_support_fact_item(
                    package,
                    villager_id,
                    "schedule",
                    "text",
                    text_value=text,
                    scope_id=f"schedule:{stable_part(support_entity.id)}",
                    condition_set_id=None,
                    ordinal=0,
                    locator_id=locator_id,
                    transformation_rule="official-npc-schedule-to-player-facts-v1",
                )
        elif support_entity.entity_type == "villager_gift":
            for ordinal, (preference, item) in enumerate(gift_fact_items(attributes, by_id)):
                add_support_fact_item(
                    package,
                    villager_id,
                    "gift_preferences",
                    "text",
                    text_value=item,
                    scope_id=(
                        f"gift:{stable_part(support_entity.id)}:"
                        f"{stable_part(preference)}:{ordinal}"
                    ),
                    condition_set_id=None,
                    ordinal=ordinal,
                    locator_id=locator_id,
                    transformation_rule="official-villager-gifts-to-player-facts-v1",
                )
    package.source_documents = sorted(documents.values(), key=lambda item: item.id)
    package.source_locators = sorted(locators.values(), key=lambda item: item.id)


def schedule_fact_text(attributes: dict[str, Any]) -> str | None:
    location = text_value(attributes.get("location") or attributes.get("Location"))
    time = text_value(attributes.get("time") or attributes.get("Time"))
    schedule = text_value(attributes.get("schedule") or attributes.get("Schedule"))
    entries = attributes.get("ScheduleEntries")
    if isinstance(entries, list):
        rendered_entries: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_time = entry.get("time")
            entry_location = text_value(entry.get("location"))
            route = entry.get("route")
            if isinstance(entry_time, int) and entry_location:
                route_text = (
                    " ".join(str(item) for item in route) if isinstance(route, list) else ""
                )
                rendered_entries.append(
                    f"{entry_time}：{entry_location}{(' ' + route_text) if route_text else ''}"
                )
            else:
                rule = text_value(entry.get("rule"))
                if rule:
                    rendered_entries.append(f"规则：{rule}")
        if rendered_entries:
            schedule = "；".join(rendered_entries)
    parts = [
        part
        for part in (
            f"时间：{time}" if time else None,
            f"地点：{location}" if location else None,
        )
        if part
    ]
    if schedule:
        parts.append(schedule)
    return "；".join(parts) or None


def gift_fact_items(
    attributes: dict[str, Any], by_id: dict[str, NormalizedEntity]
) -> list[tuple[str, str]]:
    tastes = attributes.get("GiftTastes")
    if isinstance(tastes, list):
        result: list[tuple[str, str]] = []
        for taste in tastes:
            if not isinstance(taste, dict):
                continue
            preference = text_value(taste.get("preference")) or "unknown"
            values = taste.get("items")
            values = values if isinstance(values, list) else [values]
            for value in values:
                rendered = render_gift_reference(value, by_id)
                if rendered is not None:
                    result.append((preference, rendered))
        return result
    raw = attributes.get("items") or attributes.get("Items") or attributes.get("itemIds")
    values = raw if isinstance(raw, list) else [raw]
    return [
        ("unknown", rendered)
        for value in values
        if (rendered := render_gift_reference(value, by_id)) is not None
    ]


def render_gift_reference(
    value: object, by_id: dict[str, NormalizedEntity]
) -> str | None:
    reference = stable_entity_reference(value, by_id)
    if reference is not None:
        return reference
    raw = text_value(value)
    if raw is None:
        return None
    if raw.startswith("category_"):
        return f"类别引用：{raw.removeprefix('category_')}"
    if raw.startswith("-") or raw.isdigit():
        return f"官方分类引用：{raw}"
    return f"未解析礼物引用：{raw}"


def _fixture_attributes(entity: NormalizedEntity) -> dict[str, Any]:
    attributes = dict(entity.extra_json)
    attributes.setdefault("_stagingFixture", True)
    fields = attributes.get("legacyFields")
    if entity.entity_type == "fish" and isinstance(fields, list):
        attributes.update(
            {
                "Difficulty": legacy_int(fields, 1),
                "Behavior": legacy_text(fields, 2),
                "MinSize": legacy_int(fields, 3),
                "MaxSize": legacy_int(fields, 4),
                "FishingTime": legacy_text(fields, 5),
                "Seasons": [
                    item.strip()
                    for item in str(legacy_text(fields, 6) or "").split()
                    if item.strip()
                ],
                "Weather": legacy_text(fields, 7),
            }
        )
    if entity.entity_type in {"cooking_recipe", "crafting_recipe"} and isinstance(fields, list):
        ingredients = parse_ingredients(fields[0]) if fields else None
        if ingredients:
            attributes["Ingredients"] = ingredients
    return attributes


def add_typed_support_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
    entity_ids: set[str],
    game_version: str,
    locators_by_entity: dict[str, str] | None = None,
) -> None:
    """Project stable support references without exposing raw support JSON.

    C1 publishes typed fishing locations and purchase offers. Every support row
    keeps its own stable scope, condition set, locator, and claim evidence;
    unsupported or unresolved values are not serialized as arbitrary JSON.
    """
    by_id = {entity.id: entity for entity in entities}
    source_documents: dict[str, Schema5SourceDocument] = {
        item.id: item for item in package.source_documents
    }
    source_locators: dict[str, Schema5SourceLocator] = {
        item.id: item for item in package.source_locators
    }
    source = Schema5SourceDocument(
        id="source:official-support:locations",
        source_kind="official_derived",
        title="Data/Locations.json",
        game_version=game_version,
    )
    source_documents[source.id] = source
    mine_source = Schema5SourceDocument(
        id="source:official-rule:mine-fishing",
        source_kind="official_derived",
        title="Stardew Valley.dll · MineShaft.getFish",
        game_version=game_version,
    )
    source_documents[mine_source.id] = mine_source
    references = build_reference_index(entities, support, by_id)
    for fish_id, fish_references in build_fish_support_references(support, by_id).items():
        slot_key = "fishing_locations"
        if any(
            slot.id == f"fact:{fish_id}:{slot_key}" and slot.status == "not_applicable"
            for slot in package.fact_slots
        ):
            continue
        sorted_references = sorted(fish_references, key=fish_reference_key)
        reference_keys = [fish_reference_key(reference) for reference in sorted_references]
        if len(reference_keys) != len(set(reference_keys)):
            raise ValueError(f"鱼类地点规则缺少可区分稳定键：{fish_id}")
        for ordinal, reference in enumerate(sorted_references):
            slot_id = f"fact:{fish_id}:{slot_key}"
            reference_key = fish_reference_key(reference)
            item_key = stable_part(reference_key)
            is_mine_rule = reference.get("sourceMethod") is not None
            locator = Schema5SourceLocator(
                id=f"locator:official-support:locations:{stable_part(fish_id)}:{item_key}",
                source_document_id=mine_source.id if is_mine_rule else source.id,
                source_file=(
                    str(reference.get("sourceFile"))
                    if is_mine_rule
                    else "Data/Locations.json"
                ),
                json_path=(
                    None
                    if is_mine_rule
                    else f"$.{reference['locationId']}.Fish[*]"
                ),
                record_key=(
                    str(reference.get("sourceMethod"))
                    if is_mine_rule
                    else fish_id
                ),
            )
            source_locators[locator.id] = locator
            ensure_support_fact_slot(
                package,
                entity_id=fish_id,
                slot_key=slot_key,
                value_type="text",
                locator_id=locator.id,
                transformation_rule="official-locations-to-player-facts-v1",
            )
            item_id = f"fact-item:{fish_id}:{slot_key}:{item_key}"
            condition, condition_terms = fish_condition(reference, item_id)
            condition_id = condition.id if condition is not None else None
            if condition is not None:
                package.condition_sets.append(condition)
                package.condition_terms.extend(condition_terms)
            fact_item = Schema5FactItem(
                id=item_id,
                slot_id=slot_id,
                ordinal=ordinal,
                value_type="text",
                text_value=str(reference["locationId"]),
                scope_id=f"fishing:{fish_id}:{item_key}",
                condition_set_id=condition_id,
            )
            package.fact_items.append(fact_item)
            add_support_facet(
                package,
                entity_id=fish_id,
                family="fishing_location",
                item=fact_item,
                condition_set_id=condition_id,
                locator_id=locator.id,
                transformation_rule="official-locations-to-player-facts-v1",
            )
            evidence_id = f"evidence:fact-item:{stable_part(item_id)}"
            package.evidence.append(
                Schema5Evidence(
                    id=evidence_id,
                    source_locator_id=locator.id,
                    evidence_kind="derived",
                    transformation_rule="official-locations-to-player-facts-v1",
                    input_claim_id=fish_id,
                )
            )
            package.claim_evidence.append(Schema5ClaimEvidence(item_id, evidence_id, "fact_item"))
    for monster_id, monster_references in references.monster_locations.items():
        sorted_references = sorted(monster_references, key=monster_location_key)
        reference_keys = [monster_location_key(reference) for reference in sorted_references]
        if len(reference_keys) != len(set(reference_keys)):
            raise ValueError(f"怪物地点规则缺少可区分稳定键：{monster_id}")
        for ordinal, reference in enumerate(sorted_references):
            reference_key = reference_keys[ordinal]
            item_key = stable_part(reference_key)
            locator = Schema5SourceLocator(
                id=f"locator:official-support:locations:{stable_part(monster_id)}:{item_key}",
                source_document_id=source.id,
                source_file="Data/Locations.json",
                json_path=f"$.{reference['locationId']}.Monsters[*]",
                record_key=monster_id,
            )
            source_locators[locator.id] = locator
            condition_id = opaque_rule_condition(
                package,
                f"condition:monster-location:{item_key}",
                reference,
            )
            item = add_support_fact_item(
                package,
                monster_id,
                "locations",
                "text",
                text_value=str(reference["locationId"]),
                scope_id=f"monster-location:{stable_part(monster_id)}:{item_key}",
                condition_set_id=condition_id,
                ordinal=ordinal,
                locator_id=locator.id,
                transformation_rule="official-locations-monster-to-player-facts-v1",
            )
            add_support_facet(
                package,
                entity_id=monster_id,
                family="monster_location",
                item=item,
                condition_set_id=condition_id,
                locator_id=locator.id,
                transformation_rule="official-locations-monster-to-player-facts-v1",
            )
    add_purchase_offer_projections(
        package,
        entities,
        support,
        source_documents,
        source_locators,
        game_version,
        locators_by_entity or {},
    )
    add_weapon_acquisition_projections(
        package,
        entities,
        support,
        source_documents,
        source_locators,
        game_version,
    )
    add_machine_and_usage_projections(
        package,
        entities,
        support,
        source_documents,
        source_locators,
        game_version,
    )
    package.source_documents = sorted(source_documents.values(), key=lambda item: item.id)
    package.source_locators = sorted(source_locators.values(), key=lambda item: item.id)


def add_purchase_offer_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
    source_documents: dict[str, Schema5SourceDocument],
    source_locators: dict[str, Schema5SourceLocator],
    game_version: str,
    locators_by_entity: dict[str, str],
) -> None:
    """Project official shop offers without turning sale prices into purchase prices.

    ``ShopBuilder.GetBasePrice`` starts from an explicit offer price, otherwise
    uses either object-data ``Price`` (only when requested) or the runtime
    sale-price rule.  The latter, profit margins, random modifier amounts and
    conditional modifiers cannot always be evaluated from static JSON, so they
    become an explicit dynamic rule instead of an invented coin price.
    """
    by_id = {entity.id: entity for entity in entities}
    resolver = ItemReferenceResolver.create(by_id)
    indexed_offers: dict[str, list[dict[str, object]]] = defaultdict(list)
    build_shop_index(indexed_offers, support.shops, resolver)
    source = Schema5SourceDocument(
        id="source:official-support:shops",
        source_kind="official_derived",
        title="Data/Shops.json",
        game_version=game_version,
    )
    source_documents[source.id] = source
    for entity in entities:
        slot_prefix = "seed_purchase" if entity.entity_type == "crop" else "purchase"
        offers = list(indexed_offers.get(entity.id, ()))
        price_target = entity
        seed_entity_id: str | None = None
        if entity.entity_type == "crop":
            # Crops are keyed by harvest item in Crops.json; their buyable
            # entity is the explicitly linked seed object, never a coincident
            # crop key or another random offer candidate.
            seed_entity_id = stable_item_reference(
                structured_attributes(entity).get("SeedItemId"), by_id
            )
            if seed_entity_id is not None:
                offers.extend(indexed_offers.get(seed_entity_id, ()))
                price_target = by_id[seed_entity_id]
        if not offers:
            if entity.entity_type == "crop":
                ensure_missing_purchase_slot(
                    package,
                    entity,
                    "seed_purchase_price",
                    locators_by_entity.get(entity.id),
                    "not_applicable" if seed_entity_id is not None else "not_collected",
                )
            elif entity.entity_type in {"big_craftable", "tool", "weapon"}:
                ensure_not_applicable_purchase_slot(
                    package, entity, "purchase_price", locators_by_entity.get(entity.id)
                )
            continue

        sorted_offers = sorted(offers, key=shop_offer_key)
        offer_keys = [shop_offer_key(offer) for offer in sorted_offers]
        if len(offer_keys) != len(set(offer_keys)):
            raise ValueError(f"商店报价缺少可区分稳定键：{entity.id}")
        coin_price_written = False
        non_coin_offer_written = False
        dynamic_price_written = False
        for ordinal, (offer_key, offer) in enumerate(zip(offer_keys, sorted_offers, strict=True)):
            scope_id = f"offer:{stable_part(offer_key)}"
            locator = Schema5SourceLocator(
                id=f"locator:official-support:shops:{stable_part(offer_key)}",
                source_document_id=source.id,
                source_file="Data/Shops.json",
                json_path=f"$.{offer['shopId']}.Items[*]",
                record_key=str(offer_key),
            )
            source_locators[locator.id] = locator
            condition, condition_terms = shop_condition(offer, entity.id, slot_prefix, offer_key)
            condition_id = condition.id if condition is not None else None
            if condition is not None:
                package.condition_sets.append(condition)
                package.condition_terms.extend(condition_terms)

            currency = currency_label(offer.get("currency"))
            if currency is not None:
                add_support_fact_item(
                    package, entity.id, f"{slot_prefix}_currency", "text",
                    text_value=currency, scope_id=scope_id, condition_set_id=condition_id,
                    ordinal=ordinal, locator_id=locator.id,
                    transformation_rule="official-shops-to-player-facts-v1",
                )
            price = resolve_shop_offer_price(offer, price_target, by_id)
            diagnostic = {
                "shopId": offer.get("shopId"),
                "offerKey": offer_key,
                "entityId": entity.id,
                "scopeId": scope_id,
                "currency": currency,
                "conditioned": condition_id is not None,
                **price,
            }
            dynamic_reason = out_of_season_price_rule(offer)
            if dynamic_reason is not None:
                diagnostic["dynamicRule"] = dynamic_reason
            package.shop_price_diagnostics.append(diagnostic)
            if price["kind"] == "coin" and currency == "金币":
                price_item = add_support_fact_item(
                    package, entity.id, f"{slot_prefix}_price", "integer",
                    integer_value=price["value"], scope_id=scope_id,
                    condition_set_id=condition_id, ordinal=ordinal, locator_id=locator.id,
                    transformation_rule="official-shop-builder-get-base-price-v1",
                    input_claim_id=price.get("inputClaimId"),
                )
                coin_price_written = True
                add_support_facet(
                    package, entity_id=entity.id, family=f"{slot_prefix}_price",
                    item=price_item, condition_set_id=condition_id, locator_id=locator.id,
                    transformation_rule="official-shop-builder-get-base-price-v1",
                )
                if dynamic_reason is not None:
                    add_dynamic_price_rule(
                        package, entity.id, slot_prefix, scope_id, condition_id, ordinal,
                        locator.id, dynamic_reason, price.get("inputClaimId"),
                    )
            elif price["kind"] == "currency_amount" and currency is not None:
                non_coin_offer_written = True
                add_support_fact_item(
                    package, entity.id, f"{slot_prefix}_currency_amount", "integer",
                    integer_value=price["value"], scope_id=scope_id,
                    condition_set_id=condition_id, ordinal=ordinal, locator_id=locator.id,
                    transformation_rule="official-shop-builder-get-base-price-v1",
                    input_claim_id=price.get("inputClaimId"),
                )
            elif price["kind"] == "dynamic":
                dynamic_price_written = True
                ensure_dynamic_price_slot(
                    package,
                    entity.id,
                    slot_prefix,
                    locator.id,
                    str(price["reason"]),
                    price.get("inputClaimId"),
                )
                add_dynamic_price_rule(
                    package, entity.id, slot_prefix, scope_id, condition_id, ordinal,
                    locator.id, str(price["reason"]), price.get("inputClaimId"),
                )

            trade_item = offer.get("tradeItemId")
            if price["kind"] == "exchange_only":
                non_coin_offer_written = True
            resolved_trade_items = resolver.resolve(trade_item)
            trade_amount = offer.get("tradeItemAmount")
            if len(resolved_trade_items) == 1:
                add_support_fact_item(
                    package, entity.id, f"{slot_prefix}_exchange_item_id", "text",
                    text_value=resolved_trade_items[0], scope_id=scope_id,
                    condition_set_id=condition_id, ordinal=ordinal, locator_id=locator.id,
                    transformation_rule="official-shops-to-player-facts-v1",
                )
                if isinstance(trade_amount, int) and not isinstance(trade_amount, bool):
                    add_support_fact_item(
                        package, entity.id, f"{slot_prefix}_exchange_amount", "integer",
                        integer_value=trade_amount, scope_id=scope_id,
                        condition_set_id=condition_id, ordinal=ordinal, locator_id=locator.id,
                        transformation_rule="official-shops-to-player-facts-v1",
                    )
        if entity.entity_type == "crop" and not coin_price_written:
            ensure_not_collected_purchase_slot(
                package, entity, "seed_purchase_price", locators_by_entity.get(entity.id)
            )
        elif entity.entity_type in {"big_craftable", "tool", "weapon"} and not coin_price_written:
            # An offer paid only in a special currency or another item has no
            # gold purchase price by definition. Keep its quoted cost in the
            # scoped currency/exchange slots instead of penalizing coverage as
            # an uncollected coin price.
            if non_coin_offer_written and not dynamic_price_written:
                ensure_not_applicable_purchase_slot(
                    package, entity, "purchase_price", locators_by_entity.get(entity.id)
                )
            else:
                ensure_not_collected_purchase_slot(
                    package, entity, "purchase_price", locators_by_entity.get(entity.id)
                )


def add_weapon_acquisition_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
    source_documents: dict[str, Schema5SourceDocument],
    source_locators: dict[str, Schema5SourceLocator],
    game_version: str,
) -> None:
    """Project auditable weapon acquisition methods from official rules.

    Weapon records do not contain a player-facing acquisition field.  Shop
    rows and the item branches in the official game code are therefore
    published as text fact items, with floor/shop conditions kept separately.
    ``MineBaseLevel`` is intentionally never used as an acquisition answer.
    """
    weapons = {
        entity.id: entity
        for entity in entities
        if entity.entity_type == "weapon"
    }
    if not weapons:
        return
    by_id = {entity.id: entity for entity in entities}
    resolver = ItemReferenceResolver.create(by_id)
    counters: dict[str, int] = defaultdict(int)
    shops_source_id = "source:official-support:shops"
    source_documents.setdefault(
        shops_source_id,
        Schema5SourceDocument(
            id=shops_source_id,
            source_kind="official_derived",
            title="Data/Shops.json",
            game_version=game_version,
        ),
    )
    indexed_offers: dict[str, list[dict[str, object]]] = defaultdict(list)
    build_shop_index(indexed_offers, support.shops, resolver)
    for entity_id in sorted(weapons):
        offers = sorted(indexed_offers.get(entity_id, ()), key=shop_offer_key)
        for offer in offers:
            offer_key = shop_offer_key(offer)
            locator_id = f"locator:official-support:shops:{stable_part(offer_key)}"
            source_locators.setdefault(
                locator_id,
                Schema5SourceLocator(
                    id=locator_id,
                    source_document_id=shops_source_id,
                    source_file="Data/Shops.json",
                    json_path=f"$.{offer['shopId']}.Items[*]",
                    record_key=offer_key,
                ),
            )
            condition, terms = shop_condition(
                offer, entity_id, "acquisition", offer_key
            )
            condition_id = condition.id if condition is not None else None
            if condition is not None and not any(
                item.id == condition.id for item in package.condition_sets
            ):
                package.condition_sets.append(condition)
                package.condition_terms.extend(terms)
            shop_id = str(offer.get("shopId") or "")
            if shop_id.startswith("DesertFestival"):
                text = "节日兑换获得"
            elif offer.get("tradeItemId") is not None:
                text = "兑换获得"
            else:
                text = "商店购买"
            _add_weapon_acquisition_item(
                package,
                entity_id,
                text,
                scope_id=f"weapon-acquisition:shop:{stable_part(offer_key)}",
                condition_set_id=condition_id,
                locator_id=locator_id,
                ordinal=counters[entity_id],
                transformation_rule="official-shops-to-weapon-acquisition-v1",
            )
            counters[entity_id] += 1

    special_source_id = "source:official-rule:special-weapon-acquisition"
    source_documents.setdefault(
        special_source_id,
        Schema5SourceDocument(
            id=special_source_id,
            source_kind="official_derived",
            title="Stardew Valley.dll · special weapon acquisition rules",
            game_version=game_version,
        ),
    )
    for weapon_id, (text, record_key, transformation_rule) in sorted(
        SPECIAL_WEAPON_ACQUISITION_RULES.items(), key=lambda item: int(item[0])
    ):
        entity_id = f"weapon:{weapon_id}"
        if entity_id not in weapons:
            continue
        locator_id = _weapon_rule_locator(
            source_locators,
            special_source_id,
            "Stardew Valley.dll",
            record_key,
        )
        condition_id = _special_weapon_condition(package, weapon_id)
        _add_weapon_acquisition_item(
            package,
            entity_id,
            text,
            scope_id=f"weapon-acquisition:special:{weapon_id}",
            condition_set_id=condition_id,
            locator_id=locator_id,
            ordinal=counters[entity_id],
            transformation_rule=transformation_rule,
        )
        counters[entity_id] += 1

    mine_source_id = "source:official-rule:mine-weapon-acquisition"
    source_documents.setdefault(
        mine_source_id,
        Schema5SourceDocument(
            id=mine_source_id,
            source_kind="official_derived",
            title="Stardew Valley.dll · MineShaft weapon reward rules",
            game_version=game_version,
        ),
    )
    for weapon_id, ranges in sorted(
        MINE_SPECIAL_WEAPON_RULES.items(), key=lambda item: int(item[0])
    ):
        entity_id = f"weapon:{weapon_id}"
        if entity_id not in weapons:
            continue
        locator_id = _weapon_rule_locator(
            source_locators,
            mine_source_id,
            "Stardew Valley.dll",
            "MineShaft.getSpecialItemForThisMineLevel",
        )
        for minimum, maximum in ranges:
            condition_id = _weapon_floor_condition(
                package,
                condition_prefix=(
                    f"condition:weapon-mine-special:{weapon_id}:{minimum}"
                ),
                minimum=minimum,
                maximum=maximum,
            )
            _add_weapon_acquisition_item(
                package,
                entity_id,
                "矿井特殊掉落",
                scope_id=(
                    f"weapon-acquisition:mine-special:{weapon_id}:{minimum}"
                ),
                condition_set_id=condition_id,
                locator_id=locator_id,
                ordinal=counters[entity_id],
                transformation_rule="official-mine-special-item-to-weapon-acquisition-v1",
            )
            counters[entity_id] += 1

    for weapon_id, floor in sorted(
        MINE_STANDARD_CHEST_WEAPONS.items(), key=lambda item: int(item[0])
    ):
        entity_id = f"weapon:{weapon_id}"
        if entity_id not in weapons:
            continue
        locator_id = _weapon_rule_locator(
            source_locators,
            mine_source_id,
            "Stardew Valley.dll",
            "MineShaft.addLevelChests",
        )
        condition_id = _weapon_chest_condition(
            package,
            f"condition:weapon-mine-standard:{weapon_id}",
            floor,
            "normal",
        )
        _add_weapon_acquisition_item(
            package,
            entity_id,
            "矿井固定层宝箱",
            scope_id=f"weapon-acquisition:mine-standard:{weapon_id}",
            condition_set_id=condition_id,
            locator_id=locator_id,
            ordinal=counters[entity_id],
            transformation_rule="official-mine-chest-to-weapon-acquisition-v1",
        )
        counters[entity_id] += 1

    for weapon_id, floors in sorted(
        MINE_REMIXED_CHEST_WEAPONS.items(), key=lambda item: int(item[0])
    ):
        entity_id = f"weapon:{weapon_id}"
        if entity_id not in weapons:
            continue
        locator_id = _weapon_rule_locator(
            source_locators,
            mine_source_id,
            "Stardew Valley.dll",
            "MineShaft.GetReplacementChestItem",
        )
        for floor in floors:
            condition_id = _weapon_chest_condition(
                package,
                f"condition:weapon-mine-remixed:{weapon_id}:{floor}",
                floor,
                "remixed",
            )
            _add_weapon_acquisition_item(
                package,
                entity_id,
                "重混矿井宝箱",
                scope_id=f"weapon-acquisition:mine-remixed:{weapon_id}:{floor}",
                condition_set_id=condition_id,
                locator_id=locator_id,
                ordinal=counters[entity_id],
                transformation_rule="official-remixed-mine-chest-to-weapon-acquisition-v1",
            )
            counters[entity_id] += 1

    fishing_source_id = "source:official-rule:fishing-treasure"
    source_documents.setdefault(
        fishing_source_id,
        Schema5SourceDocument(
            id=fishing_source_id,
            source_kind="official_derived",
            title="Stardew Valley.dll · FishingRod.openTreasureMenuEndFunction",
            game_version=game_version,
        ),
    )
    for weapon_id in ("14", "51"):
        entity_id = f"weapon:{weapon_id}"
        if entity_id not in weapons:
            continue
        locator_id = _weapon_rule_locator(
            source_locators,
            fishing_source_id,
            "Stardew Valley.dll",
            "FishingRod.openTreasureMenuEndFunction",
        )
        _add_weapon_acquisition_item(
            package,
            entity_id,
            "钓鱼宝箱",
            scope_id=f"weapon-acquisition:fishing-treasure:{weapon_id}",
            condition_set_id=None,
            locator_id=locator_id,
            ordinal=counters[entity_id],
            transformation_rule="official-fishing-treasure-to-weapon-acquisition-v1",
        )
        counters[entity_id] += 1

    volcano_source_id = "source:official-rule:volcano-chest"
    source_documents.setdefault(
        volcano_source_id,
        Schema5SourceDocument(
            id=volcano_source_id,
            source_kind="official_derived",
            title="Stardew Valley.dll · VolcanoDungeon.PopulateChest",
            game_version=game_version,
        ),
    )
    for weapon_id, _chest_type in sorted(
        VOLCANO_CHEST_WEAPONS.items(), key=lambda item: int(item[0])
    ):
        entity_id = f"weapon:{weapon_id}"
        if entity_id not in weapons:
            continue
        locator_id = _weapon_rule_locator(
            source_locators,
            volcano_source_id,
            "Stardew Valley.dll",
            "VolcanoDungeon.PopulateChest",
        )
        _add_weapon_acquisition_item(
            package,
            entity_id,
            "火山地牢宝箱",
            scope_id=f"weapon-acquisition:volcano-chest:{weapon_id}",
            condition_set_id=None,
            locator_id=locator_id,
            ordinal=counters[entity_id],
            transformation_rule="official-volcano-chest-to-weapon-acquisition-v1",
        )
        counters[entity_id] += 1

    quests_source_id = "source:official-support:monster-slayer-quests"
    source_documents.setdefault(
        quests_source_id,
        Schema5SourceDocument(
            id=quests_source_id,
            source_kind="official_direct",
            title="Data/MonsterSlayerQuests.json",
            game_version=game_version,
        ),
    )
    for quest_id, quest in sorted(support.monster_slayer_quests.items()):
        if not isinstance(quest, dict):
            continue
        reward = quest.get("RewardItemId")
        if not isinstance(reward, str) or reward != "(W)13":
            continue
        entity_id = "weapon:13"
        if entity_id not in weapons:
            continue
        locator_id = f"locator:official-support:monster-slayer-quests:{stable_part(quest_id)}"
        source_locators.setdefault(
            locator_id,
            Schema5SourceLocator(
                id=locator_id,
                source_document_id=quests_source_id,
                source_file="Data/MonsterSlayerQuests.json",
                json_path=f"$.{quest_id}.RewardItemId",
                record_key=quest_id,
            ),
        )
        _add_weapon_acquisition_item(
            package,
            entity_id,
            "冒险家公会怪物猎杀任务奖励",
            scope_id=f"weapon-acquisition:monster-slayer:{quest_id}",
            condition_set_id=None,
            locator_id=locator_id,
            ordinal=counters[entity_id],
            transformation_rule="official-monster-slayer-reward-to-weapon-acquisition-v1",
        )
        counters[entity_id] += 1


def _add_weapon_acquisition_item(
    package: Schema5Package,
    entity_id: str,
    text: str,
    *,
    scope_id: str,
    condition_set_id: str | None,
    locator_id: str,
    ordinal: int,
    transformation_rule: str,
) -> None:
    add_support_fact_item(
        package,
        entity_id,
        "acquisition",
        "text",
        text_value=text,
        scope_id=scope_id,
        condition_set_id=condition_set_id,
        ordinal=ordinal,
        locator_id=locator_id,
        transformation_rule=transformation_rule,
    )


def _weapon_rule_locator(
    source_locators: dict[str, Schema5SourceLocator],
    source_document_id: str,
    source_file: str,
    record_key: str,
) -> str:
    locator_id = f"locator:official-rule:weapon-acquisition:{stable_part(record_key)}"
    source_locators.setdefault(
        locator_id,
        Schema5SourceLocator(
            id=locator_id,
            source_document_id=source_document_id,
            source_file=source_file,
            record_key=record_key,
        ),
    )
    return locator_id


def _special_weapon_condition(
    package: Schema5Package,
    weapon_id: str,
) -> str:
    conditions = {
        "4": ("需要七彩碎片，并在沙漠三柱处触发规则", "prismatic_shard_desert_pillars"),
        "47": ("新存档初始工具", "new_game_start"),
        "53": ("采石场矿井尽头的黄金镰刀交互规则", "quarry_mine_golden_scythe"),
        "62": ("银河剑和 3 个银河之魂", "galaxy_sword_plus_three_souls"),
        "63": ("银河之锤和 3 个银河之魂", "galaxy_hammer_plus_three_souls"),
        "64": ("银河匕首和 3 个银河之魂", "galaxy_dagger_plus_three_souls"),
        "61": ("挑战矿井额外难度规则奖励", "mine_challenge_reward"),
        "66": ("耕种精通奖励可领取", "farming_mastery_reward"),
    }
    summary, kind = conditions[weapon_id]
    condition_id = f"condition:weapon-special:{weapon_id}"
    if not any(item.id == condition_id for item in package.condition_sets):
        package.condition_sets.append(
            Schema5ConditionSet(
                id=condition_id,
                completeness="complete",
                player_summary=summary,
            )
        )
        package.condition_terms.append(
            Schema5ConditionTerm(
                id=f"condition-term:{stable_part(condition_id)}:rule",
                condition_set_id=condition_id,
                ordinal=0,
                kind=kind,
                value_text=summary,
            )
        )
    return condition_id


def _weapon_floor_condition(
    package: Schema5Package,
    condition_prefix: str,
    minimum: int,
    maximum: int | None,
) -> str:
    terms = [
        Schema5ConditionTerm(
            id=f"condition-term:{stable_part(condition_prefix)}:min",
            condition_set_id=condition_prefix,
            ordinal=0,
            kind="mine_floor_min",
            value_integer=minimum,
        )
    ]
    summary = f"矿井第 {minimum} 层起"
    if maximum is not None:
        terms.append(
            Schema5ConditionTerm(
                id=f"condition-term:{stable_part(condition_prefix)}:max",
                condition_set_id=condition_prefix,
                ordinal=1,
                kind="mine_floor_max",
                value_integer=maximum,
            )
        )
        summary = f"矿井第 {minimum}-{maximum} 层"
    if not any(item.id == condition_prefix for item in package.condition_sets):
        package.condition_sets.append(
            Schema5ConditionSet(
                id=condition_prefix,
                completeness="complete",
                player_summary=summary,
            )
        )
        package.condition_terms.extend(terms)
    return condition_prefix


def _weapon_chest_condition(
    package: Schema5Package,
    condition_id: str,
    floor: int,
    mode: str,
) -> str:
    if not any(item.id == condition_id for item in package.condition_sets):
        package.condition_sets.append(
            Schema5ConditionSet(
                id=condition_id,
                completeness="complete",
                player_summary=(
                    f"{('重混' if mode == 'remixed' else '普通')}矿井第 {floor} 层固定宝箱"
                ),
            )
        )
        package.condition_terms.extend(
            [
                Schema5ConditionTerm(
                    id=f"condition-term:{stable_part(condition_id)}:floor",
                    condition_set_id=condition_id,
                    ordinal=0,
                    kind="mine_floor",
                    value_integer=floor,
                ),
                Schema5ConditionTerm(
                    id=f"condition-term:{stable_part(condition_id)}:mode",
                    condition_set_id=condition_id,
                    ordinal=1,
                    kind="mine_chest_mode",
                    value_text=mode,
                ),
            ]
        )
    return condition_id


def ensure_not_applicable_purchase_slot(
    package: Schema5Package,
    entity: NormalizedEntity,
    slot_key: str,
    locator_id: str | None,
) -> None:
    ensure_missing_purchase_slot(package, entity, slot_key, locator_id, "not_applicable")


def ensure_not_collected_purchase_slot(
    package: Schema5Package,
    entity: NormalizedEntity,
    slot_key: str,
    locator_id: str | None,
) -> None:
    ensure_missing_purchase_slot(package, entity, slot_key, locator_id, "not_collected")


def ensure_missing_purchase_slot(
    package: Schema5Package,
    entity: NormalizedEntity,
    slot_key: str,
    locator_id: str | None,
    status: str,
) -> None:
    if locator_id is None or any(
        slot.id == f"fact:{entity.id}:{slot_key}" for slot in package.fact_slots
    ):
        return
    package.fact_slots.append(
        Schema5FactSlot(
            id=f"fact:{entity.id}:{slot_key}",
            entity_id=entity.id,
            slot_key=slot_key,
            status=status,
        )
    )
    package.claim_evidence.append(
        direct_claim(f"fact:{entity.id}:{slot_key}", "fact_slot", locator_id, package)
    )


def resolve_shop_offer_price(
    offer: dict[str, object],
    target: NormalizedEntity,
    by_id: dict[str, NormalizedEntity],
) -> dict[str, object]:
    """Mirror the statically knowable part of ``ShopBuilder.GetBasePrice``.

    The game first uses the offer price (defaulting to ``-1``), then maps a
    negative price to zero for a trade, object-data ``Price`` only when the
    explicit flag requests it, or the runtime item's sale-price rule.  Shop
    modifiers run first unless explicitly ignored; item modifiers run second.
    Any runtime-dependent branch remains a typed dynamic rule, never an
    object sale price disguised as a purchase price.
    """
    trade_item = offer.get("tradeItemId")
    raw_price = offer.get("price", -1)
    if not isinstance(raw_price, int) or isinstance(raw_price, bool):
        return {"kind": "dynamic", "reason": "invalid-or-missing-price"}
    input_claim_id: str | None = None
    if raw_price < 0:
        if trade_item is not None:
            # GetBasePrice yields zero for a negative-price trade, then the
            # same shop/item modifier chain still runs. A zero result is only
            # the exchange cost; a positive modifier result is a separate
            # coin component of that same scoped offer.
            raw_price = 0
        elif offer.get("useObjectDataPrice") is True:
            object_id = object_price_entity_id(target, by_id)
            object_entity = by_id.get(object_id) if object_id else None
            object_price = (
                structured_attributes(object_entity).get("Price")
                if object_entity is not None
                else None
            )
            if isinstance(object_price, int) and not isinstance(object_price, bool):
                raw_price = object_price
                input_claim_id = object_id
            else:
                return {
                    "kind": "dynamic",
                    "reason": "object-data-price-unresolved",
                    "inputClaimId": object_id,
                }
        else:
            object_id = object_price_entity_id(target, by_id)
            object_entity = by_id.get(object_id) if object_id else None
            runtime_price = runtime_object_sale_price(object_entity)
            if runtime_price is None:
                return {
                    "kind": "dynamic",
                    "reason": "runtime-sale-price",
                    "inputClaimId": object_id,
                }
            raw_price = runtime_price
            input_claim_id = object_id

    if requires_runtime_profit_margin(offer, target, by_id):
        return {
            "kind": "dynamic",
            "reason": "runtime-profit-margin",
            "inputClaimId": input_claim_id,
        }
    modifiers = active_shop_price_modifiers(offer)
    if modifiers is None:
        return {
            "kind": "dynamic",
            "reason": "conditional-or-random-price-modifier",
            "inputClaimId": input_claim_id,
        }
    adjusted = apply_price_modifiers(
        float(raw_price), modifiers["shop"], str(offer.get("shopPriceModifierMode") or "Stack")
    )
    adjusted = apply_price_modifiers(
        adjusted, modifiers["item"], str(offer.get("priceModifierMode") or "Stack")
    )
    if adjusted is None:
        return {
            "kind": "dynamic",
            "reason": "unsupported-price-modifier",
            "inputClaimId": input_claim_id,
        }
    value = int(adjusted)
    currency = currency_label(offer.get("currency"))
    exchange_only = trade_item is not None and value == 0
    return {
        "kind": (
            "exchange_only"
            if exchange_only
            else ("coin" if currency == "金币" else "currency_amount")
        ),
        "value": value,
        "inputClaimId": input_claim_id,
        "reason": "trade-item-cost" if exchange_only else "static-official-shop-price",
        "appliedShopModifiers": len(modifiers["shop"]),
        "appliedItemModifiers": len(modifiers["item"]),
    }


def runtime_object_sale_price(target: NormalizedEntity | None) -> int | None:
    """Evaluate Object.salePrice(true) only for its stable, ordinary branch."""
    if target is None or target.entity_type != "object":
        return None
    price = structured_attributes(target).get("Price")
    if not isinstance(price, int) or isinstance(price, bool):
        return None
    # Object.salePrice contains item-ID, fence and recipe branches that cannot
    # be proven from Shops/Objects alone. Keep those dynamic rather than guess.
    if target.game_id in {"378", "380", "382", "384", "388", "390"}:
        return None
    if structured_attributes(target).get("IsRecipe") is True:
        return None
    return price * 2


def requires_runtime_profit_margin(
    offer: dict[str, object],
    target: NormalizedEntity,
    by_id: dict[str, NormalizedEntity],
) -> bool:
    explicit = offer.get("itemApplyProfitMargins")
    if explicit is None:
        explicit = offer.get("shopApplyProfitMargins")
    if explicit is True:
        return True
    if explicit is False:
        return False
    object_id = object_price_entity_id(target, by_id)
    object_entity = by_id.get(object_id) if object_id else None
    return (
        object_entity is not None
        and structured_attributes(object_entity).get("Category") == -74
    )


def object_price_entity_id(
    target: NormalizedEntity,
    by_id: dict[str, NormalizedEntity],
) -> str | None:
    """Use the offer target's Object row, never a sibling random candidate."""
    candidate = f"object:{target.game_id}" if target.game_id else ""
    return candidate if candidate in by_id else None


def active_shop_price_modifiers(
    offer: dict[str, object],
) -> dict[str, list[dict[str, object]]] | None:
    shop = [] if offer.get("ignoreShopPriceModifiers") is True else modifier_rows(
        offer.get("shopPriceModifiers")
    )
    item = modifier_rows(offer.get("priceModifiers"))
    if shop is None or item is None:
        return None
    return {"shop": shop, "item": item}


def modifier_rows(value: object) -> list[dict[str, object]] | None:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        return None
    rows: list[dict[str, object]] = []
    for modifier in value:
        if not isinstance(modifier, dict):
            return None
        if (
            modifier.get("Condition") not in (None, "")
            or modifier.get("RandomAmount") not in (None, [])
        ):
            return None
        amount = modifier.get("Amount")
        if not isinstance(amount, int | float) or isinstance(amount, bool):
            return None
        rows.append(modifier)
    return rows


def apply_price_modifiers(
    value: float,
    modifiers: list[dict[str, object]],
    mode: str,
) -> float | None:
    """Reproduce ``Utility.ApplyQuantityModifiers`` for static modifier rows."""
    selected: float | None = None
    for modifier in modifiers:
        # Utility uses the original base for Minimum/Maximum, but chains Stack.
        base = (
            value
            if mode in {"Minimum", "Maximum"}
            else (selected if selected is not None else value)
        )
        candidate = apply_price_modifier(base, modifier)
        if candidate is None:
            return None
        if mode == "Minimum":
            selected = candidate if selected is None else min(selected, candidate)
        elif mode == "Maximum":
            selected = candidate if selected is None else max(selected, candidate)
        else:
            selected = candidate
    return value if selected is None else selected


def apply_price_modifier(value: float, modifier: dict[str, object]) -> float | None:
    amount = float(modifier["Amount"])
    operation = modifier.get("Modification")
    if operation == "Add":
        return value + amount
    if operation == "Multiply":
        return value * amount
    if operation == "Divide" and amount != 0:
        return value / amount
    if operation in {"Set", "Override"}:
        return amount
    return None


def ensure_dynamic_price_slot(
    package: Schema5Package,
    entity_id: str,
    slot_prefix: str,
    locator_id: str,
    reason: str,
    input_claim_id: object,
) -> None:
    """Mark a core price question answered when only a runtime rule is knowable.

    A dynamic offer intentionally has no integer ``*_price`` fact item.  Its
    companion ``*_price_rule`` item explains why.  The price slot itself must
    nevertheless be ``dynamic_rule`` so coverage distinguishes a supported
    runtime rule from an uncollected price.
    """
    ensure_support_fact_slot(
        package,
        entity_id=entity_id,
        slot_key=f"{slot_prefix}_price",
        value_type="text",
        locator_id=locator_id,
        transformation_rule="official-shop-builder-dynamic-price-rule-v1",
        input_claim_id=str(input_claim_id) if input_claim_id else None,
        status="dynamic_rule",
    )


def add_dynamic_price_rule(
    package: Schema5Package,
    entity_id: str,
    slot_prefix: str,
    scope_id: str,
    condition_set_id: str | None,
    ordinal: int,
    locator_id: str,
    reason: str,
    input_claim_id: object,
) -> None:
    add_support_fact_item(
        package,
        entity_id,
        f"{slot_prefix}_price_rule",
        "text",
        text_value=reason,
        scope_id=scope_id,
        condition_set_id=condition_set_id,
        ordinal=ordinal,
        locator_id=locator_id,
        transformation_rule="official-shop-builder-dynamic-price-rule-v1",
        input_claim_id=str(input_claim_id) if input_claim_id else None,
        status="dynamic_rule",
    )


def add_machine_and_usage_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
    source_documents: dict[str, Schema5SourceDocument],
    source_locators: dict[str, Schema5SourceLocator],
    game_version: str,
) -> None:
    """Project machine-use and recipe reverse references as scoped typed rows."""
    by_id = {entity.id: entity for entity in entities}
    references = build_reference_index(entities, support, by_id)
    machine_source = Schema5SourceDocument(
        id="source:official-support:machines",
        source_kind="official_derived",
        title="Data/Machines.json",
        game_version=game_version,
    )
    source_documents[machine_source.id] = machine_source
    for entity_id, rows in sorted(references.machine_uses.items()):
        for ordinal, reference in enumerate(sorted(rows, key=machine_reference_key)):
            machine_id = reference.get("machineId")
            machine_entity_id = stable_entity_reference(machine_id, by_id)
            if machine_entity_id is None:
                continue
            rule_id = str(reference.get("ruleId") or "rule")
            trigger_id = str(reference.get("triggerId") or "trigger")
            locator = Schema5SourceLocator(
                id=(
                    "locator:official-support:machines:"
                    f"{stable_part(entity_id)}:{stable_part(machine_id or 'machine')}"
                    f":{stable_part(rule_id)}:{stable_part(trigger_id)}"
                ),
                source_document_id=machine_source.id,
                source_file="Data/Machines.json",
                json_path=f"$.{machine_id}.OutputRules[*].Triggers[*]",
                record_key=trigger_id,
            )
            source_locators[locator.id] = locator
            condition_id = opaque_rule_condition(
                package,
                f"condition:machine:{stable_part(entity_id)}:{stable_part(rule_id)}:{stable_part(trigger_id)}",
                reference,
            )
            scope_id = (
                f"machine:{stable_part(machine_id or 'machine')}:{stable_part(rule_id)}:"
                f"{stable_part(trigger_id)}"
            )
            add_support_fact_item(
                package,
                entity_id,
                "machine_uses",
                "text",
                text_value=machine_entity_id,
                scope_id=scope_id,
                condition_set_id=condition_id,
                ordinal=ordinal,
                locator_id=locator.id,
                transformation_rule="official-machines-to-player-facts-v1",
            )
            required_count = int_value(reference.get("requiredCount"))
            if required_count is not None:
                add_support_fact_item(
                    package,
                    entity_id,
                    "machine_use_required_count",
                    "integer",
                    integer_value=required_count,
                    scope_id=scope_id,
                    condition_set_id=condition_id,
                    ordinal=ordinal,
                    locator_id=locator.id,
                    transformation_rule="official-machines-to-player-facts-v1",
                )
            ready_minutes = int_value(reference.get("minutesUntilReady"))
            if ready_minutes is not None:
                add_support_fact_item(
                    package,
                    entity_id,
                    "machine_use_minutes",
                    "integer",
                    integer_value=ready_minutes,
                    scope_id=scope_id,
                    condition_set_id=condition_id,
                    ordinal=ordinal,
                    locator_id=locator.id,
                    transformation_rule="official-machines-to-player-facts-v1",
                )

    for entity_id, rows in sorted(references.used_in.items()):
        for ordinal, reference in enumerate(sorted(rows, key=usage_reference_key)):
            usage_id = text_value(reference.get("usageId"))
            if usage_id is None:
                continue
            usage_entity_id = (
                usage_id
                if usage_id in by_id
                else stable_entity_reference(usage_id, by_id)
            )
            if usage_entity_id is None:
                continue
            usage_entity = by_id[usage_entity_id]
            usage_source_file = str(
                reference.get("_source") or usage_entity.source_file
            ).replace("\\", "/")
            digest = hashlib.sha256(usage_source_file.encode("utf-8")).hexdigest()[:16]
            document_id = f"source:official-usage:{digest}"
            usage_document = Schema5SourceDocument(
                id=document_id,
                source_kind="official_derived",
                title=usage_source_file,
                game_version=game_version,
            )
            source_documents[document_id] = usage_document
            locator = Schema5SourceLocator(
                id=f"locator:official-usage:{stable_part(usage_entity_id)}:{stable_part(entity_id)}",
                source_document_id=document_id,
                source_file=usage_source_file,
                record_key=usage_id,
            )
            source_locators[locator.id] = locator
            scope_id = f"usage:{stable_part(usage_entity_id)}"
            add_support_fact_item(
                package,
                entity_id,
                "used_in",
                "text",
                text_value=usage_entity_id,
                scope_id=scope_id,
                condition_set_id=None,
                ordinal=ordinal,
                locator_id=locator.id,
                transformation_rule="official-usage-to-player-facts-v1",
            )
            quantity = int_value(reference.get("quantity"))
            if quantity is not None:
                add_support_fact_item(
                    package,
                    entity_id,
                    "used_in_quantity",
                    "integer",
                    integer_value=quantity,
                    scope_id=scope_id,
                    condition_set_id=None,
                    ordinal=ordinal,
                    locator_id=locator.id,
                    transformation_rule="official-usage-to-player-facts-v1",
                )
            quality = text_value(reference.get("quality"))
            if quality is not None:
                add_support_fact_item(
                    package,
                    entity_id,
                    "used_in_quality",
                    "text",
                    text_value=quality,
                    scope_id=scope_id,
                    condition_set_id=None,
                    ordinal=ordinal,
                    locator_id=locator.id,
                    transformation_rule="official-usage-to-player-facts-v1",
                )


def machine_reference_key(reference: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(reference.get("machineId") or ""),
        str(reference.get("ruleId") or ""),
        str(reference.get("triggerId") or ""),
    )


def usage_reference_key(reference: dict[str, object]) -> tuple[str, str]:
    return (str(reference.get("usageId") or ""), str(reference.get("usageType") or ""))


def opaque_rule_condition(
    package: Schema5Package,
    condition_id: str,
    reference: dict[str, object],
) -> str | None:
    fields = {
        key: reference.get(key)
        for key in (
            "condition",
            "requiredTags",
            "requiredCount",
            "minDepth",
            "maxDepth",
            "minTime",
            "maxTime",
        )
        if reference.get(key) is not None
    }
    if not fields:
        return None
    if any(condition.id == condition_id for condition in package.condition_sets):
        return condition_id
    package.condition_sets.append(
        Schema5ConditionSet(
            id=condition_id,
            completeness="opaque",
            player_summary="官方规则受游戏条件限制",
            original_text=json.dumps(fields, ensure_ascii=False, sort_keys=True),
        )
    )
    package.condition_terms.append(
        Schema5ConditionTerm(
            id=f"condition-term:{stable_part(condition_id)}:rule",
            condition_set_id=condition_id,
            ordinal=0,
            kind="rule",
            value_text=json.dumps(fields, ensure_ascii=False, sort_keys=True),
        )
    )
    return condition_id


def ensure_support_fact_slot(
    package: Schema5Package,
    *,
    entity_id: str,
    slot_key: str,
    value_type: str,
    locator_id: str,
    transformation_rule: str,
    input_claim_id: str | None = None,
    status: str = "fixed",
) -> str:
    slot_id = f"fact:{entity_id}:{slot_key}"
    existing = next((slot for slot in package.fact_slots if slot.id == slot_id), None)
    if existing is not None:
        # A direct typed fact may legitimately coexist with conditional shop
        # offers; its status describes that direct answer, while each offer
        # item retains its own condition and scope.
        return slot_id
    package.fact_slots.append(
        Schema5FactSlot(
            id=slot_id,
            entity_id=entity_id,
            slot_key=slot_key,
            status=status,
            value_type=value_type,
        )
    )
    evidence_id = f"evidence:fact-slot:{stable_part(slot_id)}"
    package.evidence.append(
        Schema5Evidence(
            id=evidence_id,
            source_locator_id=locator_id,
            evidence_kind="derived",
            transformation_rule=transformation_rule,
            input_claim_id=input_claim_id or entity_id,
        )
    )
    package.claim_evidence.append(Schema5ClaimEvidence(slot_id, evidence_id, "fact_slot"))
    return slot_id


def add_support_fact_item(
    package: Schema5Package,
    entity_id: str,
    slot_key: str,
    value_type: str,
    *,
    text_value: str | None = None,
    integer_value: int | None = None,
    scope_id: str,
    condition_set_id: str | None,
    ordinal: int,
    locator_id: str,
    transformation_rule: str,
    input_claim_id: str | None = None,
    status: str = "fixed",
) -> Schema5FactItem:
    slot_id = ensure_support_fact_slot(
        package,
        entity_id=entity_id,
        slot_key=slot_key,
        value_type=value_type,
        locator_id=locator_id,
        transformation_rule=transformation_rule,
        input_claim_id=input_claim_id,
        status=status,
    )
    item_id = f"fact-item:{entity_id}:{slot_key}:{stable_part(scope_id)}"
    fact_item = Schema5FactItem(
        id=item_id,
        slot_id=slot_id,
        ordinal=ordinal,
        value_type=value_type,
        text_value=text_value,
        integer_value=integer_value,
        scope_id=scope_id,
        condition_set_id=condition_set_id,
    )
    package.fact_items.append(fact_item)
    evidence_id = f"evidence:fact-item:{stable_part(item_id)}"
    package.evidence.append(
        Schema5Evidence(
            id=evidence_id,
            source_locator_id=locator_id,
            evidence_kind="derived",
            transformation_rule=transformation_rule,
            input_claim_id=input_claim_id or entity_id,
        )
    )
    package.claim_evidence.append(Schema5ClaimEvidence(item_id, evidence_id, "fact_item"))
    return fact_item


def add_crop_season_facets(
    package: Schema5Package,
    entity_id: str,
    seasons: object,
    input_claim_id: str,
    locator_id: str,
) -> None:
    if not isinstance(seasons, list):
        return
    values = sorted(
        {
            season_label(item)
            for item in seasons
            if season_label(item) is not None
        }
    )
    if not values:
        return
    family = "season"
    group_id = f"facet-group:{entity_id}:{family}"
    package.facet_groups.append(
        Schema5FacetGroup(group_id, entity_id, family, "fixed")
    )
    for value in values:
        scope_id = f"crop-season:{entity_id}"
        facet_id = f"facet:{entity_id}:{family}:{stable_part(value)}"
        package.facets.append(
            Schema5Facet(
                id=facet_id,
                group_id=group_id,
                scope_family=family,
                scope_id=scope_id,
                value_type="text",
                text_value=value,
                claim_status="fixed",
            )
        )
        evidence_id = f"evidence:facet:{stable_part(facet_id)}"
        package.evidence.append(
            Schema5Evidence(
                id=evidence_id,
                source_locator_id=locator_id,
                evidence_kind="derived",
                transformation_rule="official-crop-seasons-to-browse-facet-v1",
                input_claim_id=input_claim_id,
            )
        )
        package.claim_evidence.append(Schema5ClaimEvidence(facet_id, evidence_id, "facet"))


def season_label(value: object) -> str | None:
    labels = {
        "spring": "春季",
        "summer": "夏季",
        "fall": "秋季",
        "autumn": "秋季",
        "winter": "冬季",
    }
    if not isinstance(value, str):
        return None
    return labels.get(value.strip().casefold())


def add_support_facet(
    package: Schema5Package,
    *,
    entity_id: str,
    family: str,
    item: Schema5FactItem,
    condition_set_id: str | None,
    locator_id: str,
    transformation_rule: str,
) -> None:
    group_id = f"facet-group:{entity_id}:{family}"
    claim_status = "conditional" if condition_set_id else "fixed"
    group_index = next(
        (index for index, group in enumerate(package.facet_groups) if group.id == group_id),
        None,
    )
    if group_index is None:
        package.facet_groups.append(
            Schema5FacetGroup(group_id, entity_id, family, claim_status)
        )
    elif package.facet_groups[group_index].status == "fixed" and claim_status == "conditional":
        package.facet_groups[group_index] = Schema5FacetGroup(
            group_id, entity_id, family, claim_status
        )
    facet_id = f"facet:{entity_id}:{family}:{stable_part(item.scope_id or item.id)}"
    if any(facet.id == facet_id for facet in package.facets):
        return
    package.facets.append(
        Schema5Facet(
            id=facet_id,
            group_id=group_id,
            scope_family=family,
            scope_id=item.scope_id or item.id,
            value_type=item.value_type,
            text_value=item.text_value,
            integer_value=item.integer_value,
            condition_set_id=condition_set_id,
            claim_status=claim_status,
        )
    )
    evidence_id = f"evidence:facet:{stable_part(facet_id)}"
    package.evidence.append(
        Schema5Evidence(
            id=evidence_id,
            source_locator_id=locator_id,
            evidence_kind="derived",
            transformation_rule=transformation_rule,
            input_claim_id=item.id,
        )
    )
    package.claim_evidence.append(Schema5ClaimEvidence(facet_id, evidence_id, "facet"))


def shop_offer_key(offer: dict[str, object]) -> str:
    shop_id = str(offer.get("shopId") or "").strip()
    offer_id = str(offer.get("offerId") or "").strip()
    if offer_id:
        return f"shop:{shop_id}:offer:{offer_id}"
    item_id = str(offer.get("itemId") or "").strip()
    random_ids = offer.get("randomItemIds")
    if not item_id and isinstance(random_ids, list):
        item_id = "|".join(sorted(str(item) for item in random_ids))
    if not shop_id or not item_id:
        raise ValueError("商店报价缺少稳定店铺或商品 ID")
    return f"shop:{shop_id}:item:{item_id}"


def currency_label(value: object) -> str | None:
    # ShopData defaults Currency to money when the JSON omits the field.
    if value is None:
        return "金币"
    labels = {
        "0": "金币",
        "1": "星星币",
        "2": "赌场币",
        "4": "齐钻",
        "Money": "金币",
        "QiCoins": "齐钻",
        "StarTokens": "星星币",
        "FestivalTokens": "节日代币",
    }
    return labels.get(str(value)) if value is not None else None


def out_of_season_price_rule(offer: dict[str, object]) -> str | None:
    """Expose ShopBuilder's SeedShop/PierreStocklist 1.5× runtime branch."""
    condition = offer.get("condition")
    if (
        offer.get("shopId") == "SeedShop"
        and isinstance(condition, str)
        and "SEASON" in condition.upper()
    ):
        return "out-of-season-price-rule"
    return None


def shop_condition(
    offer: dict[str, object],
    entity_id: str,
    slot_prefix: str,
    offer_key: str,
) -> tuple[Schema5ConditionSet | None, list[Schema5ConditionTerm]]:
    fields = {
        key: offer[key]
        for key in ("condition", "perItemCondition")
        if offer.get(key) not in (None, "", [], {})
    }
    # Static modifier rows have already been applied in the same order as the
    # runtime builder and do not make the result conditional. Retain only
    # modifiers that depend on a game state or random draw as quote rules.
    for key in ("priceModifiers", "shopPriceModifiers"):
        modifiers = offer.get(key)
        if has_dynamic_price_modifier(modifiers):
            fields[key] = modifiers
    if not fields:
        return None, []
    condition_id = f"condition:{entity_id}:{slot_prefix}:{stable_part(offer_key)}"
    terms = [
        Schema5ConditionTerm(
            id=f"condition-term:{stable_part(condition_id)}:{stable_part(key)}",
            condition_set_id=condition_id,
            ordinal=ordinal,
            kind="rule",
            value_text=(
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False, sort_keys=True)
            ),
        )
        for ordinal, (key, value) in enumerate(sorted(fields.items()))
    ]
    return (
        Schema5ConditionSet(
            id=condition_id,
            completeness="opaque",
            player_summary="商店报价受游戏条件或价格规则限制",
            original_text=json.dumps(
                fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        ),
        terms,
    )


def has_dynamic_price_modifier(value: object) -> bool:
    if not isinstance(value, list):
        return value not in (None, [])
    return any(
        not isinstance(modifier, dict)
        or modifier.get("Condition") not in (None, "")
        or modifier.get("RandomAmount") not in (None, [])
        for modifier in value
    )


def build_fish_support_references(
    support: OfficialSupportData,
    by_id: dict[str, NormalizedEntity],
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for location_id, location in support.locations.items():
        fish_rows = location.get("Fish")
        if not isinstance(fish_rows, list):
            continue
        for row in fish_rows:
            if not isinstance(row, dict):
                continue
            item_id = row.get("ItemId")
            if isinstance(item_id, str) and item_id.startswith("(O)"):
                item_id = item_id[3:]
            fish_id = f"fish:{item_id}" if isinstance(item_id, str) else ""
            if fish_id in by_id:
                result.setdefault(fish_id, []).append(
                    {
                        "locationId": location_id,
                        "areaId": row.get("FishAreaId"),
                        "season": row.get("Season"),
                        "chance": row.get("Chance"),
                        "condition": row.get("Condition"),
                        "minFishingLevel": row.get("MinFishingLevel"),
                        "minDistanceFromShore": row.get("MinDistanceFromShore"),
                        "maxDistanceFromShore": row.get("MaxDistanceFromShore"),
                    }
                )
    add_mine_fishing_references(result, by_id)
    return result


def add_mine_fishing_references(
    result: dict[str, list[dict[str, object]]],
    by_id: dict[str, NormalizedEntity],
) -> None:
    """Add the MineShaft rules not represented by ``Data/Locations.json``.

    The official mine fishing implementation selects these items by mine-area
    bands: Stonefish for levels 1-10, Ice Pip for 40-79, and Lava Eel for
    80-120.  Keep the rule and its source method explicit instead of treating
    the object record as a fishing location or inventing a generic mine row.
    """
    rules = (
        ("fish:158", "Mine", 1, 10, 0.02, 0.01, "Stonefish"),
        ("fish:161", "Mine", 40, 79, 0.015, 0.009, "Ice Pip"),
        ("fish:162", "Mine", 80, 120, 0.01, 0.008, "Lava Eel"),
    )
    for fish_id, location_id, min_depth, max_depth, base_chance, level_chance, bait in rules:
        if fish_id not in by_id:
            continue
        result.setdefault(fish_id, []).append(
            {
                "locationId": location_id,
                "areaId": "mine",
                "chance": base_chance,
                "minDepth": min_depth,
                "maxDepth": max_depth,
                "fishingLevelChance": level_chance,
                "baitHint": bait,
                "sourceFile": "Stardew Valley.dll",
                "sourceMethod": "StardewValley.Locations.MineShaft.getFish",
            }
        )


def stable_reference_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def monster_location_key(reference: dict[str, object]) -> str:
    location_id = str(reference.get("locationId") or "").strip()
    if not location_id:
        raise ValueError("怪物地点规则缺少稳定地点 ID")
    return "|".join(
        [
            location_id,
            *(
                stable_reference_value(reference.get(key))
                for key in ("condition", "minDepth", "maxDepth", "minTime", "maxTime")
            ),
        ]
    )


def fish_reference_key(reference: dict[str, object]) -> str:
    location_id = str(reference.get("locationId") or "").strip()
    if not location_id:
        raise ValueError("鱼类地点规则缺少稳定地点 ID")
    parts = [
        location_id,
        *(
            stable_reference_value(reference.get(key))
            for key in (
                "areaId",
                "season",
                "chance",
                "condition",
                "minFishingLevel",
                "minDistanceFromShore",
                "maxDistanceFromShore",
                "minDepth",
                "maxDepth",
                "fishingLevelChance",
                "baitHint",
            )
        ),
    ]
    return "|".join(parts)


def fish_condition(
    reference: dict[str, object],
    item_id: str,
) -> tuple[Schema5ConditionSet | None, list[Schema5ConditionTerm]]:
    fields = {
        key: value
        for key, value in reference.items()
        if key not in {
            "locationId",
            "areaId",
            "sourceFile",
            "sourceMethod",
        }
        and value is not None
        and value != ""
    }
    if not fields:
        return None, []
    condition_id = f"condition:{stable_part(item_id)}"
    terms: list[Schema5ConditionTerm] = []
    summaries: list[str] = []
    unparsed = False
    recognized = {
        "season": "季节",
        "chance": "出现概率",
        "condition": "游戏条件",
        "minFishingLevel": "最低钓鱼等级",
        "minDistanceFromShore": "离岸最小距离",
        "maxDistanceFromShore": "离岸最大距离",
        "minDepth": "矿井起始层",
        "maxDepth": "矿井结束层",
        "fishingLevelChance": "钓鱼等级影响概率",
        "baitHint": "针对性鱼饵提示",
    }
    for key in sorted(fields):
        value = fields[key]
        term_id = f"condition-term:{stable_part(condition_id)}:{stable_part(key)}"
        if key == "season":
            season_values = value if isinstance(value, list) else [value]
            text = ",".join(str(item).strip() for item in season_values if str(item).strip())
            if not text:
                continue
            terms.append(
                Schema5ConditionTerm(
                    term_id, condition_id, len(terms), "season", value_text=text
                )
            )
            summaries.append(f"季节：{text}")
        elif key == "condition" and isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            terms.append(
                Schema5ConditionTerm(
                    term_id, condition_id, len(terms), "rule", value_text=text
                )
            )
            summaries.append("游戏条件：另有未识别限制")
        elif key == "chance" and isinstance(value, int | float) and not isinstance(value, bool):
            terms.append(
                Schema5ConditionTerm(
                    term_id, condition_id, len(terms), "chance", value_real=float(value)
                )
            )
            summaries.append(f"出现概率：{value}")
        elif (
            key == "fishingLevelChance"
            and isinstance(value, int | float)
            and not isinstance(value, bool)
        ):
            terms.append(
                Schema5ConditionTerm(
                    term_id,
                    condition_id,
                    len(terms),
                    "fishing_level_chance",
                    value_real=float(value),
                )
            )
            summaries.append(f"钓鱼等级影响概率：{value}")
        elif key == "baitHint" and isinstance(value, str):
            terms.append(
                Schema5ConditionTerm(
                    term_id, condition_id, len(terms), "bait_hint", value_text=value
                )
            )
            summaries.append(f"针对性鱼饵：{value}")
        elif (
            key in {
                "minFishingLevel",
                "minDistanceFromShore",
                "maxDistanceFromShore",
                "minDepth",
                "maxDepth",
            }
            and isinstance(value, int)
            and not isinstance(value, bool)
        ):
            terms.append(
                Schema5ConditionTerm(
                    term_id, condition_id, len(terms), key, value_integer=value
                )
            )
            summaries.append(f"{recognized[key]}：{value}")
        else:
            unparsed = True
            terms.append(
                Schema5ConditionTerm(
                    term_id,
                    condition_id,
                    len(terms),
                    "unparsed",
                    value_text=json.dumps(
                        value, ensure_ascii=False, sort_keys=True
                    ),
                )
            )
    unknown = [key for key in fields if key not in recognized]
    if unknown or unparsed:
        completeness = "partial"
        original_text = json.dumps(
            fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    elif any(term.kind == "rule" for term in terms):
        completeness = "opaque"
        original_text = json.dumps(
            fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    else:
        completeness = "complete"
        original_text = None
    return (
        Schema5ConditionSet(
            id=condition_id,
            completeness=completeness,
            player_summary="；".join(summaries) or None,
            original_text=original_text,
        ),
        terms,
    )


def to_schema_entity(entity: NormalizedEntity) -> Schema5Entity:
    return Schema5Entity(
        id=entity.id,
        entity_type=entity.entity_type,
        game_id=entity.game_id,
        internal_name=entity.internal_name,
        name_zh=entity.name_zh,
        name_en=entity.name_en,
        description_zh=entity.description_zh,
        description_en=entity.description_en,
        category=entity.category,
        translation_status=entity.translation_status,
        aliases=tuple(entity.aliases),
        sort_key=entity.name_zh or entity.id,
    )


def to_card(entity: NormalizedEntity) -> Schema5EntityCard:
    return Schema5EntityCard(
        entity_id=entity.id,
        identity_summary=entity.description_zh or entity.description_en,
        category_label=entity.category,
        sort_key=entity.name_zh or entity.id,
    )


def source_for_entity(
    entity: NormalizedEntity,
    game_version: str,
) -> tuple[Schema5SourceDocument, Schema5SourceLocator]:
    source_file = entity.source_file.replace("\\", "/")
    digest = hashlib.sha256(source_file.encode("utf-8")).hexdigest()[:16]
    document_id = f"source:official:{digest}"
    locator_id = f"locator:{digest}:{stable_part(entity.id)}"
    return (
        Schema5SourceDocument(
            id=document_id,
            source_kind="official_direct",
            title=source_file,
            game_version=game_version,
        ),
        Schema5SourceLocator(
            id=locator_id,
            source_document_id=document_id,
            source_file=source_file,
            record_key=entity.game_id or entity.id,
        ),
    )


def visuals_for_entity(
    entity: NormalizedEntity,
    output_dir: Path,
    entity_ids: set[str],
) -> list[Schema5Visual]:
    path = entity.image_path
    attributes = structured_attributes(entity)
    if path:
        image_file = (output_dir / path).resolve()
        try:
            image_file.relative_to(output_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"物化图片路径越界：{entity.id}") from exc
        if not image_file.is_file():
            raise ValueError(f"物化图片不存在：{entity.id}")
        relative = path.replace("\\", "/")
        sha256 = sha256_file(image_file)
        crop_rect = crop_rect_value(attributes, entity.image_crop_rect)
        rule_version = "legacy-visual-v1"
        if is_explicit_visual_reuse(entity):
            source_entity_id = proxy_source_entity(entity, entity_ids)
            return [
                Schema5Visual(
                    id=f"visual:{entity.id}:entity",
                    entity_id=entity.id,
                    role="entity",
                    status="official_reuse",
                    relative_path=relative,
                    sha256=sha256,
                    source_entity_id=source_entity_id,
                    crop_rect=crop_rect,
                    rule_version=rule_version,
                    reuse_reason="引用关联人物展示视觉",
                )
            ]
        return [
            Schema5Visual(
                id=f"visual:{entity.id}:entity",
                entity_id=entity.id,
                role="entity",
                status="official_own",
                relative_path=relative,
                sha256=sha256,
                crop_rect=crop_rect,
                rule_version=rule_version,
            )
        ]
    if attributes.get("imageRequired") is True:
        raise ValueError(f"必需视觉尚未物化：{entity.id}")
    if attributes.get("imageAvailability") == "not_applicable":
        return [
            Schema5Visual(
                id=f"visual:{entity.id}:entity",
                entity_id=entity.id,
                role="entity",
                status="official_none",
                rule_version="legacy-visual-v1",
                reuse_reason="官方图片不适用于该实体",
            )
        ]
    return [
        Schema5Visual(
            id=f"visual:{entity.id}:entity",
            entity_id=entity.id,
            role="entity",
            status="official_none",
        )
    ]


def is_explicit_visual_reuse(entity: NormalizedEntity) -> bool:
    return (
        entity.entity_type == "villager_gift"
        and structured_attributes(entity).get("imageRequired") is False
    )


def proxy_source_entity(entity: NormalizedEntity, entity_ids: set[str]) -> str:
    if entity.entity_type == "villager_gift" and entity.game_id:
        candidate = f"villager:{entity.game_id}"
        if candidate in entity_ids:
            return candidate
    if entity.entity_type == "villager_gift" and entity.game_id:
        candidate = f"villager:{entity.game_id.split(':', 1)[0]}"
        if candidate in entity_ids:
            return candidate
    raise ValueError(f"代理视觉缺少可解析来源实体：{entity.id}")


def crop_rect_value(
    attributes: dict[str, Any],
    materialized_rect: tuple[int, int, int, int] | None,
) -> str | None:
    value = list(materialized_rect) if materialized_rect is not None else (
        attributes.get("imageRect") or attributes.get("imageFallbackRect")
    )
    if value is None and isinstance(attributes.get("spriteIndex"), int):
        raise ValueError("视觉缺少物化裁切矩形")
    if (
        not isinstance(value, list)
        or len(value) != 4
        or not all(isinstance(item, int) for item in value)
    ):
        raise ValueError("视觉缺少确定裁切矩形")
    if value[2] <= 0 or value[3] <= 0:
        raise ValueError("视觉裁切矩形无效")
    return json.dumps(value, separators=(",", ":"))


def add_drop_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    by_id: dict[str, NormalizedEntity],
    locators_by_entity: dict[str, str],
) -> None:
    """Bind parsed official drop records to the monster's scoped fact items."""
    drops_by_monster: dict[str, list[NormalizedEntity]] = defaultdict(list)
    for drop in entities:
        if drop.entity_type != "drop":
            continue
        raw_monster = structured_attributes(drop).get("monsterId")
        if not isinstance(raw_monster, str) or not raw_monster.strip():
            continue
        monster_id = raw_monster.strip()
        if ":" in monster_id:
            monster_id = monster_id.split(":", 1)[1]
        monster_id = f"monster:{monster_id.replace(' ', '-')}"
        if monster_id in by_id:
            drops_by_monster[monster_id].append(drop)
    for monster_id, drops in sorted(drops_by_monster.items()):
        for ordinal, drop in enumerate(sorted(drops, key=lambda item: item.id)):
            attributes = structured_attributes(drop)
            item_reference = stable_entity_reference(attributes.get("itemId"), by_id)
            locator_id = locators_by_entity.get(drop.id)
            if item_reference is None or locator_id is None:
                continue
            condition_id = None
            chance = attributes.get("chance")
            if isinstance(chance, str):
                try:
                    chance = float(chance)
                except ValueError:
                    chance = None
            if isinstance(chance, int | float) and not isinstance(chance, bool):
                condition_id = f"condition:drop:{stable_part(drop.id)}"
                package.condition_sets.append(
                    Schema5ConditionSet(
                        id=condition_id,
                        completeness="complete",
                        player_summary=f"掉落概率：{chance}",
                    )
                )
                package.condition_terms.append(
                    Schema5ConditionTerm(
                        id=f"condition-term:{stable_part(condition_id)}:chance",
                        condition_set_id=condition_id,
                        ordinal=0,
                        kind="chance",
                        value_real=float(chance),
                    )
                )
            add_support_fact_item(
                package,
                monster_id,
                "drops",
                "text",
                text_value=item_reference,
                scope_id=f"drop:{stable_part(drop.id)}",
                condition_set_id=condition_id,
                ordinal=ordinal,
                locator_id=locator_id,
                transformation_rule="official-monster-drops-to-player-facts-v1",
            )


def add_inline_drop_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    by_id: dict[str, NormalizedEntity],
    locators_by_entity: dict[str, str],
) -> None:
    """Project structured monster drops when the source is a mapping record."""
    for monster in entities:
        if monster.entity_type != "monster":
            continue
        attributes = structured_attributes(monster)
        locations = join_text(attributes.get("Locations"))
        if locations is not None:
            fixed = fixed_fact(monster, "locations", "text", text_value=locations)
            if fixed is not None and not any(item.id == fixed.id for item in package.fact_slots):
                package.fact_slots.append(fixed)
                locator_id = locators_by_entity[monster.id]
                package.claim_evidence.append(fact_claim(fixed, locator_id, package))
        drops = attributes.get("Drops")
        if not isinstance(drops, list):
            continue
        locator_id = locators_by_entity[monster.id]
        for ordinal, drop in enumerate(drops):
            if not isinstance(drop, dict):
                continue
            item_reference = stable_entity_reference(drop.get("itemId"), by_id)
            if item_reference is None:
                continue
            condition_id = None
            chance = drop.get("chance")
            if isinstance(chance, int | float) and not isinstance(chance, bool):
                condition_id = f"condition:drop:{stable_part(monster.id)}:{ordinal}"
                package.condition_sets.append(
                    Schema5ConditionSet(
                        id=condition_id,
                        completeness="complete",
                        player_summary=f"掉落概率：{chance}",
                    )
                )
                package.condition_terms.append(
                    Schema5ConditionTerm(
                        id=f"condition-term:{stable_part(condition_id)}:chance",
                        condition_set_id=condition_id,
                        ordinal=0,
                        kind="chance",
                        value_real=float(chance),
                    )
                )
            add_support_fact_item(
                package,
                monster.id,
                "drops",
                "text",
                text_value=item_reference,
                scope_id=f"drop:{stable_part(monster.id)}:{ordinal}",
                condition_set_id=condition_id,
                ordinal=ordinal,
                locator_id=locator_id,
                transformation_rule="official-monster-drops-to-player-facts-v1",
            )


def relations_for_entities(
    entities: list[NormalizedEntity],
    entity_ids: set[str],
) -> list[tuple[Schema5RelationGroup, list[Schema5Relation]]]:
    rows: list[tuple[Schema5RelationGroup, list[Schema5Relation]]] = []
    for entity in entities:
        if entity.entity_type != "villager":
            continue
        attributes = structured_attributes(entity)
        friends = attributes.get("FriendsAndFamily")
        if isinstance(friends, dict):
            grouped: dict[str, list[tuple[str, str, str | None]]] = defaultdict(list)
            for target, raw_label in sorted(
                friends.items(), key=lambda item: str(item[0]).casefold()
            ):
                label = normalize_relation_label(raw_label)
                family = "kinship" if relation_predicate(label) == "kinship" else "friendship"
                grouped[family].append(
                    (
                        str(target),
                        label,
                        resolve_villager_id(str(target), entity_ids),
                    )
                )
            for family, entries in sorted(grouped.items()):
                unresolved = any(object_id is None for _, _, object_id in entries)
                relations = [
                    Schema5Relation(
                        id=f"relation:{entity.id}:{family}:{stable_part(object_id)}",
                        relation_group_id=f"group:{entity.id}:{family}",
                        subject_entity_id=entity.id,
                        predicate=relation_predicate(label),
                        object_entity_id=object_id,
                        original_direction="official",
                        label=label or None,
                    )
                    for _, label, object_id in entries
                    if object_id is not None
                ]
                rows.append(
                    (
                        Schema5RelationGroup(
                            id=f"group:{entity.id}:{family}",
                            entity_id=entity.id,
                            family=family,
                            status=(
                                "unknown" if unresolved else ("fixed" if relations else "unknown")
                            ),
                        ),
                        [] if unresolved else relations,
                    )
                )
        love_interest = attributes.get("LoveInterest")
        if isinstance(love_interest, str) and love_interest.strip():
            object_id = resolve_villager_id(love_interest, entity_ids)
            rows.append(
                (
                    Schema5RelationGroup(
                        id=f"group:{entity.id}:love_interest",
                        entity_id=entity.id,
                        family="love_interest",
                        status="fixed" if object_id is not None else "unknown",
                    ),
                    [
                        Schema5Relation(
                            id=f"relation:{entity.id}:love_interest:{stable_part(object_id)}",
                            relation_group_id=f"group:{entity.id}:love_interest",
                            subject_entity_id=entity.id,
                            predicate="love_interest_pointer",
                            object_entity_id=object_id,
                            original_direction="official",
                            label=None,
                        )
                    ]
                    if object_id is not None
                    else [],
                )
            )
    return rows


def stable_item_reference(
    value: object,
    by_id: dict[str, NormalizedEntity] | None,
) -> str | None:
    item_id = text_value(value)
    if not item_id or by_id is None:
        return None
    candidate = f"object:{item_id}"
    return candidate if candidate in by_id else None


def fact_source_entity_id(
    entity: NormalizedEntity,
    fact: Schema5FactSlot,
    by_id: dict[str, NormalizedEntity],
) -> str:
    if entity.entity_type == "crop" and fact.slot_key == "sell_price":
        harvest_id = text_value(structured_attributes(entity).get("HarvestItemId"))
        candidate = f"object:{harvest_id}" if harvest_id else ""
        if candidate in by_id:
            return candidate
    return entity.id


def source_locators_by_entity(
    entity_id: str,
    locators_by_entity: dict[str, str],
    fallback: str,
) -> str:
    return locators_by_entity.get(entity_id, fallback)


def recipe_output_facts(
    entity: NormalizedEntity,
    by_id: dict[str, NormalizedEntity],
) -> list[Schema5FactSlot]:
    if entity.entity_type not in {"cooking_recipe", "crafting_recipe"}:
        return []
    reference = stable_entity_reference(structured_attributes(entity).get("outputItemId"), by_id)
    fact = fixed_fact(entity, "crafting_output_item_id", "text", text_value=reference)
    return [fact] if fact is not None else []


def add_recipe_material_facts(
    package: Schema5Package,
    entity: NormalizedEntity,
    by_id: dict[str, NormalizedEntity],
    locator_id: str,
) -> None:
    if entity.entity_type not in {"cooking_recipe", "crafting_recipe"}:
        return
    quantities: dict[str, int] = {}
    for ingredient in recipe_ingredients(entity):
        reference = stable_entity_reference(ingredient.get("itemId"), by_id)
        quantity = ingredient.get("quantity")
        if reference is None or not isinstance(quantity, int) or quantity <= 0:
            continue
        quantities[reference] = quantities.get(reference, 0) + quantity
    for ordinal, reference in enumerate(sorted(quantities)):
        scope_id = f"recipe:{entity.id}:material:{stable_part(reference)}"
        add_support_fact_item(
            package,
            entity.id,
            "crafting_material_id",
            "text",
            text_value=reference,
            scope_id=scope_id,
            condition_set_id=None,
            ordinal=ordinal,
            locator_id=locator_id,
            transformation_rule="official-recipe-ingredients-to-player-facts-v1",
        )
        add_support_fact_item(
            package,
            entity.id,
            "crafting_material_quantity",
            "integer",
            integer_value=quantities[reference],
            scope_id=scope_id,
            condition_set_id=None,
            ordinal=ordinal,
            locator_id=locator_id,
            transformation_rule="official-recipe-ingredients-to-player-facts-v1",
        )


def recipe_ingredients(entity: NormalizedEntity) -> list[dict[str, object]]:
    attributes = structured_attributes(entity)
    ingredients = attributes.get("Ingredients")
    if isinstance(ingredients, str):
        return parse_ingredients(ingredients) or []
    if isinstance(ingredients, list):
        return [item for item in ingredients if isinstance(item, dict)]
    return []


def add_recipe_output_material_facts(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    by_id: dict[str, NormalizedEntity],
    locators_by_entity: dict[str, str],
) -> None:
    """Attach crafting recipe materials to the produced big craftable.

    Recipe rows are source records, not the player-facing crafted entity.  The
    material facts therefore keep the recipe locator and claim as provenance
    while their subject is the stable output entity.  Outputs without an
    official crafting recipe are explicitly not applicable; an existing but
    unparseable recipe remains not_collected and is not guessed from Price.
    """
    recipes_by_output: dict[str, list[NormalizedEntity]] = defaultdict(list)
    for recipe in entities:
        if recipe.entity_type != "crafting_recipe":
            continue
        output_id = stable_entity_reference(
            structured_attributes(recipe).get("outputItemId"), by_id
        )
        if output_id is not None and output_id in by_id:
            recipes_by_output[output_id].append(recipe)

    for entity in entities:
        if entity.entity_type != "big_craftable":
            continue
        recipes = sorted(recipes_by_output.get(entity.id, []), key=lambda item: item.id)
        if not recipes:
            locator_id = locators_by_entity.get(entity.id)
            ensure_not_applicable_fact_slot(
                package,
                entity,
                "crafting_material_id",
                locator_id,
            )
            ensure_not_applicable_fact_slot(
                package,
                entity,
                "crafting_material_quantity",
                locator_id,
            )
            continue
        for recipe in recipes:
            quantities: dict[str, int] = {}
            for ingredient in recipe_ingredients(recipe):
                reference = stable_entity_reference(ingredient.get("itemId"), by_id)
                quantity = ingredient.get("quantity")
                if reference is None or not isinstance(quantity, int) or quantity <= 0:
                    continue
                quantities[reference] = quantities.get(reference, 0) + quantity
            locator_id = locators_by_entity.get(recipe.id)
            if locator_id is None:
                raise ValueError(f"制作配方缺少来源定位：{recipe.id}")
            for ordinal, reference in enumerate(sorted(quantities)):
                scope_id = (
                    f"recipe-output:{stable_part(recipe.id)}:material:{stable_part(reference)}"
                )
                add_support_fact_item(
                    package,
                    entity.id,
                    "crafting_material_id",
                    "text",
                    text_value=reference,
                    scope_id=scope_id,
                    condition_set_id=None,
                    ordinal=ordinal,
                    locator_id=locator_id,
                    transformation_rule="official-recipe-output-to-player-facts-v1",
                    input_claim_id=recipe.id,
                )
                add_support_fact_item(
                    package,
                    entity.id,
                    "crafting_material_quantity",
                    "integer",
                    integer_value=quantities[reference],
                    scope_id=scope_id,
                    condition_set_id=None,
                    ordinal=ordinal,
                    locator_id=locator_id,
                    transformation_rule="official-recipe-output-to-player-facts-v1",
                    input_claim_id=recipe.id,
                )


def ensure_not_applicable_fact_slot(
    package: Schema5Package,
    entity: NormalizedEntity,
    slot_key: str,
    locator_id: str | None,
) -> None:
    if locator_id is None or any(
        slot.id == f"fact:{entity.id}:{slot_key}" for slot in package.fact_slots
    ):
        return
    fact = not_applicable_fact(entity, slot_key)
    package.fact_slots.append(fact)
    package.claim_evidence.append(direct_claim(fact.id, "fact_slot", locator_id, package))


def stable_entity_reference(
    value: object,
    by_id: dict[str, NormalizedEntity],
) -> str | None:
    candidates = sorted(
        entity_id for entity_id in entity_ids_for_item(value) if entity_id in by_id
    )
    object_candidates = [candidate for candidate in candidates if candidate.startswith("object:")]
    if len(object_candidates) == 1:
        return object_candidates[0]
    return candidates[0] if len(candidates) == 1 else None


def typed_facts(
    entity: NormalizedEntity,
    *,
    by_id: dict[str, NormalizedEntity] | None = None,
) -> list[Schema5FactSlot]:
    attributes = structured_attributes(entity)
    facts: list[Schema5FactSlot] = []
    if entity.entity_type == "villager":
        if isinstance(attributes.get("CanBeRomanced"), bool):
            facts.append(
                Schema5FactSlot(
                    id=f"fact:{entity.id}:can_be_romanced",
                    entity_id=entity.id,
                    slot_key="can_be_romanced",
                    status="fixed",
                    value_type="boolean",
                    boolean_value=attributes["CanBeRomanced"],
                )
            )
        birthday = attributes.get("BirthSeason"), attributes.get("BirthDay")
        if isinstance(birthday[0], str) and isinstance(birthday[1], int):
            facts.append(
                Schema5FactSlot(
                    id=f"fact:{entity.id}:birthday",
                    entity_id=entity.id,
                    slot_key="birthday",
                    status="fixed",
                    value_type="text",
                    text_value=f"{birthday[0]} {birthday[1]}",
                )
            )
        facts.extend(
            [
                fixed_fact(
                    entity,
                    "residence_region",
                    "text",
                    text_value=text_value(attributes.get("HomeRegion")),
                ),
                fixed_fact(
                    entity,
                    "gender",
                    "text",
                    text_value=text_value(attributes.get("Gender")),
                ),
            ]
        )
    if entity.entity_type == "crop":
        facts.extend(
            [
                fixed_fact(
                    entity, "seasons", "text", text_value=join_text(attributes.get("Seasons"))
                ),
                fixed_fact(
                    entity,
                    "first_harvest_days",
                    "integer",
                    integer_value=sum_ints(attributes.get("DaysInPhase")),
                ),
                (
                    not_applicable_fact(entity, "regrow_days")
                    if type(attributes.get("RegrowDays")) is int
                    and attributes["RegrowDays"] < 0
                    else fixed_fact(
                        entity,
                        "regrow_days",
                        "integer",
                        integer_value=nonnegative_int(attributes.get("RegrowDays")),
                    )
                ),
                fixed_fact(
                    entity,
                    "needs_watering",
                    "boolean",
                    boolean_value=bool_value(attributes.get("NeedsWatering")),
                ),
                fixed_fact(
                    entity,
                    "seed_item_id",
                    "text",
                    text_value=stable_item_reference(
                        attributes.get("SeedItemId"), by_id
                    ),
                ),
                fixed_fact(
                    entity,
                    "harvest_item_id",
                    "text",
                    text_value=stable_item_reference(
                        attributes.get("HarvestItemId"), by_id
                    ),
                ),
            ]
        )
    if entity.entity_type in {"object", "mineral", "ring"}:
        facts.append(
            fixed_fact(
                entity,
                "sell_price",
                "integer",
                integer_value=int_value(attributes.get("Price")),
            )
        )
    if entity.entity_type in {"big_craftable", "tool", "weapon"}:
        facts.extend(
            [
                fixed_fact(
                    entity,
                    "purchase_price",
                    "integer",
                    integer_value=int_value(attributes.get("PurchasePrice")),
                ),
                fixed_fact(
                    entity,
                    "upgrade_price",
                    "integer",
                    integer_value=int_value(attributes.get("UpgradeCost")),
                ),
                fixed_fact(
                    entity,
                    "upgrade_material_id",
                    "text",
                    text_value=stable_entity_reference(
                        attributes.get("UpgradeMaterial"), by_id or {}
                    ),
                ),
                fixed_fact(
                    entity,
                    "damage_min",
                    "integer",
                    integer_value=int_value(attributes.get("MinDamage")),
                ),
                fixed_fact(
                    entity,
                    "damage_max",
                    "integer",
                    integer_value=int_value(attributes.get("MaxDamage")),
                ),
                fixed_fact(
                    entity,
                    "acquisition",
                    "text",
                    text_value=text_value(attributes.get("Acquisition")),
                ),
            ]
        )
        if entity.entity_type == "tool" and not attributes.get("UpgradeMaterial"):
            facts.extend(
                [
                    not_applicable_fact(entity, "upgrade_price"),
                    not_applicable_fact(entity, "upgrade_material_id"),
                ]
            )
        if entity.entity_type == "big_craftable":
            facts.extend(
                [
                    fixed_fact(
                        entity,
                        "crafting_material_id",
                        "text",
                        text_value=stable_entity_reference(
                            attributes.get("CraftingMaterial"), by_id or {}
                        ),
                    ),
                    fixed_fact(
                        entity,
                        "crafting_material_quantity",
                        "integer",
                        integer_value=int_value(attributes.get("CraftingMaterialQuantity")),
                    ),
                ]
            )
        if entity.entity_type == "weapon":
            facts.append(
                fixed_fact(
                    entity,
                    "sell_price",
                    "integer",
                    integer_value=weapon_sell_price(entity, attributes),
                )
            )
    if entity.entity_type == "crop" and by_id is not None:
        harvest_id = text_value(attributes.get("HarvestItemId"))
        harvest = by_id.get(f"object:{harvest_id}") if harvest_id else None
        if harvest is not None:
            facts.append(
                fixed_fact(
                    entity,
                    "sell_price",
                    "integer",
                    integer_value=int_value(structured_attributes(harvest).get("Price")),
                )
            )
    if entity.entity_type == "fish":
        if attributes.get("CaptureMethod") == "trap":
            facts.extend(
                not_applicable_fact(entity, slot_key)
                for slot_key in (
                    "difficulty",
                    "behavior",
                    "min_size",
                    "max_size",
                    "fishing_time",
                    "seasons",
                    "weather",
                    "fishing_locations",
                )
            )
        else:
            facts.extend(
                [
                    fixed_fact(
                        entity,
                        "difficulty",
                        "integer",
                        integer_value=int_value(attributes.get("Difficulty")),
                    ),
                    fixed_fact(
                        entity,
                        "behavior",
                        "text",
                        text_value=text_value(attributes.get("Behavior")),
                    ),
                    fixed_fact(
                        entity,
                        "min_size",
                        "integer",
                        integer_value=int_value(attributes.get("MinSize")),
                    ),
                    fixed_fact(
                        entity,
                        "max_size",
                        "integer",
                        integer_value=int_value(attributes.get("MaxSize")),
                    ),
                    fixed_fact(
                        entity,
                        "fishing_time",
                        "text",
                        text_value=text_value(attributes.get("FishingTime")),
                    ),
                    fixed_fact(
                        entity,
                        "seasons",
                        "text",
                        text_value=join_text(attributes.get("Seasons")),
                    ),
                    fixed_fact(
                        entity,
                        "weather",
                        "text",
                        text_value=text_value(attributes.get("Weather")),
                    ),
                ]
            )
        if by_id is not None and entity.game_id:
            object_entity = by_id.get(f"object:{entity.game_id}")
            if object_entity is not None:
                facts.append(
                    fixed_fact(
                        entity,
                        "sell_price",
                        "integer",
                        integer_value=int_value(structured_attributes(object_entity).get("Price")),
                    )
                )
        if not any(fact is not None and fact.slot_key == "sell_price" for fact in facts):
            facts.append(
                fixed_fact(
                    entity,
                    "sell_price",
                    "integer",
                    integer_value=int_value(attributes.get("Price")),
                )
            )
    return [fact for fact in facts if fact is not None]


def weapon_sell_price(
    entity: NormalizedEntity,
    attributes: dict[str, Any],
) -> int | None:
    """Mirror MeleeWeapon.salePrice without treating MineBaseLevel as a price.

    Stardew's static weapon sale rule is ``getItemLevel() * 100`` except for
    the three scythes, which sell for zero.  The item-level calculation uses
    only the typed WeaponData fields and the official runtime rule, so it is a
    derived player fact with auditable source metadata rather than a raw field.
    """
    weapon_id = text_value(entity.game_id)
    if attributes.get("_stagingFixture") is True and attributes.get("Price") is not None:
        return int_value(attributes.get("Price"))
    if weapon_id in {"47", "53", "66"}:
        return 0
    min_damage = int_value(attributes.get("MinDamage"))
    max_damage = int_value(attributes.get("MaxDamage"))
    speed = int_value(attributes.get("Speed"))
    precision = int_value(attributes.get("Precision"))
    defense = int_value(attributes.get("Defense"))
    weapon_type = int_value(attributes.get("Type"))
    crit_chance = attributes.get("CritChance")
    crit_multiplier = attributes.get("CritMultiplier")
    if (
        min_damage is None
        or max_damage is None
        or speed is None
        or precision is None
        or defense is None
        or weapon_type is None
        or not isinstance(crit_chance, int | float)
        or isinstance(crit_chance, bool)
        or not isinstance(crit_multiplier, int | float)
        or isinstance(crit_multiplier, bool)
    ):
        return None
    average_damage = (min_damage + max_damage) // 2
    item_level = average_damage * (1.0 + 0.03 * (max(0, speed) + (15 if weapon_type == 1 else 0)))
    item_level += precision // 2 + defense
    item_level += (float(crit_chance) - 0.02) * 200
    item_level += (float(crit_multiplier) - 3.0) * 6
    if weapon_id == "2":
        item_level += 20
    elif weapon_id == "3":
        item_level += 15
    item_level += defense * 2
    return int(item_level / 7.0 + 1.0) * 100


def not_applicable_fact(entity: NormalizedEntity, slot_key: str) -> Schema5FactSlot:
    return Schema5FactSlot(
        id=f"fact:{entity.id}:{slot_key}",
        entity_id=entity.id,
        slot_key=slot_key,
        status="not_applicable",
        value_type=None,
    )


def fixed_fact(
    entity: NormalizedEntity,
    slot_key: str,
    value_type: str,
    *,
    text_value: str | None = None,
    integer_value: int | None = None,
    boolean_value: bool | None = None,
) -> Schema5FactSlot | None:
    if all(value is None for value in (text_value, integer_value, boolean_value)):
        return None
    return Schema5FactSlot(
        id=f"fact:{entity.id}:{slot_key}",
        entity_id=entity.id,
        slot_key=slot_key,
        status="fixed",
        value_type=value_type,
        text_value=text_value,
        integer_value=integer_value,
        boolean_value=boolean_value,
    )


def legacy_text(fields: list[object], index: int) -> str | None:
    value = fields[index] if len(fields) > index else None
    return text_value(value)


def legacy_int(fields: list[object], index: int) -> int | None:
    value = fields[index] if len(fields) > index else None
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def text_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def join_text(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    items = [str(item).strip() for item in value if str(item).strip()]
    return ",".join(items) or None


def sum_ints(value: object) -> int | None:
    if not isinstance(value, list) or not value or not all(type(item) is int for item in value):
        return None
    return sum(value)


def nonnegative_int(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def int_value(value: object) -> int | None:
    return value if type(value) is int else None


def bool_value(value: object) -> bool | None:
    return value if type(value) is bool else None


def visual_claim(
    claim_id: str,
    locator_id: str,
    package: Schema5Package,
) -> Schema5ClaimEvidence:
    evidence_id = f"evidence:visual:{stable_part(claim_id)}"
    if not any(item.id == evidence_id for item in package.evidence):
        package.evidence.append(
            Schema5Evidence(
                id=evidence_id,
                source_locator_id=locator_id,
                evidence_kind="derived",
                transformation_rule="official-asset-materialization-v1",
            )
        )
    return Schema5ClaimEvidence(
        claim_id=claim_id,
        evidence_id=evidence_id,
        claim_type="visual",
    )


def relation_claim(
    relation: Schema5Relation,
    locator_id: str,
    package: Schema5Package,
) -> Schema5ClaimEvidence:
    evidence_id = f"evidence:relation:{stable_part(relation.id)}"
    if not any(item.id == evidence_id for item in package.evidence):
        package.evidence.append(
            Schema5Evidence(
                id=evidence_id,
                source_locator_id=locator_id,
                evidence_kind="derived",
                transformation_rule="official-relation-label-normalization-v1",
            )
        )
    return Schema5ClaimEvidence(
        claim_id=relation.id,
        evidence_id=evidence_id,
        claim_type="relation",
    )


def fact_claim(
    fact: Schema5FactSlot,
    locator_id: str,
    package: Schema5Package,
    *,
    input_claim_id: str | None = None,
) -> Schema5ClaimEvidence:
    derived_slots = {"first_harvest_days", "seasons", "regrow_days", "needs_watering"}
    if (
        fact.slot_key in derived_slots
        or (fact.slot_key == "sell_price" and fact.entity_id.startswith("weapon:"))
        or input_claim_id is not None
    ):
        evidence_id = f"evidence:fact:{stable_part(fact.id)}"
        if not any(item.id == evidence_id for item in package.evidence):
            package.evidence.append(
                Schema5Evidence(
                    id=evidence_id,
                    source_locator_id=locator_id,
                    evidence_kind="derived",
                    transformation_rule=(
                        "official-crop-harvest-to-player-facts-v1"
                        if input_claim_id is not None
                        else (
                            "official-weapon-sale-rule-to-player-facts-v1"
                            if fact.slot_key == "sell_price"
                            else "official-crop-fields-to-player-facts-v1"
                        )
                    ),
                    input_claim_id=input_claim_id or fact.entity_id,
                )
            )
        return Schema5ClaimEvidence(
            claim_id=fact.id,
            evidence_id=evidence_id,
            claim_type="fact_slot",
        )
    return direct_claim(fact.id, "fact_slot", locator_id, package)


def direct_claim(
    claim_id: str,
    claim_type: str,
    locator_id: str,
    package: Schema5Package,
) -> Schema5ClaimEvidence:
    evidence_id = f"evidence:{claim_type}:{stable_part(claim_id)}"
    if not any(item.id == evidence_id for item in package.evidence):
        package.evidence.append(
            Schema5Evidence(
                id=evidence_id,
                source_locator_id=locator_id,
                evidence_kind="derived" if claim_type == "visual" else "direct",
                transformation_rule=(
                    "official-asset-materialization-v1" if claim_type == "visual" else None
                ),
            )
        )
    return Schema5ClaimEvidence(
        claim_id=claim_id, evidence_id=evidence_id, claim_type=claim_type
    )


def resolve_villager_id(value: str, entity_ids: set[str]) -> str | None:
    candidate = f"villager:{value.strip()}"
    if candidate in entity_ids:
        return candidate
    matches = [
        entity_id for entity_id in entity_ids if entity_id.casefold() == candidate.casefold()
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def normalize_relation_label(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().rstrip("]")
    key = text.rsplit(":", 1)[-1].casefold() if text else ""
    return KINSHIP_LABELS.get(key, "") if key.startswith("relative_") else key


def relation_family_from_labels(labels: object) -> str:
    if isinstance(labels, dict):
        labels = labels.values()
    if isinstance(labels, str | bytes) or not hasattr(labels, "__iter__"):
        return "friendship"
    if any(
        relation_predicate(normalize_relation_label(label)) == "kinship"
        for label in labels
    ):
        return "kinship"
    return "friendship"


def relation_predicate(label: str) -> str:
    key = label.casefold()
    if key in KINSHIP_LABELS.values() or key.startswith("relative_"):
        return "kinship"
    if key in {"friend", "friends", "friendship"}:
        return "friendship"
    if not label:
        return "friendship_unspecified"
    return "friendship_unspecified"


def stable_part(value: str) -> str:
    """Encode an identifier component without collisions or array-order dependence."""
    return quote(value, safe=":.-")
