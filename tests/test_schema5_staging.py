from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from builder.models import NormalizedEntity
from builder.pipeline.images import materialize_entity_images_with_report
from builder.pipeline.release_state import block_release
from builder.pipeline.schema5_projection import build_schema5_staging_package, stable_part
from builder.pipeline.schema5_writer import validate_schema5_package, write_schema5_package
from builder.sources.official_support import OfficialSupportData


def entity(
    entity_id: str,
    entity_type: str,
    *,
    extra_json: dict[str, object] | None = None,
    image_path: str | None = None,
    image_crop_rect: tuple[int, int, int, int] | None = None,
) -> NormalizedEntity:
    return NormalizedEntity(
        id=entity_id,
        entity_type=entity_type,
        game_id=entity_id.split(":", 1)[1],
        internal_name=None,
        name_zh=entity_id,
        name_en=None,
        description_zh=None,
        description_en=None,
        category=None,
        image_path=image_path,
        image_crop_rect=image_crop_rect,
        extra_json=extra_json or {},
        source_file="Data/Characters.json",
    )


def test_stable_id_components_do_not_collapse_distinct_values() -> None:
    assert stable_part("a/b") != stable_part("a_b")
    assert stable_part("a b") != stable_part("a-b")


def test_materializer_preserves_computed_sprite_rect(tmp_path: Path) -> None:
    source = tmp_path / "sprites.png"
    Image.new("RGBA", (32, 16), (255, 0, 0, 255)).save(source)
    result = materialize_entity_images_with_report(
        [
            entity(
                "object:1",
                "object",
                extra_json={
                    "imageSource": "sprites.png",
                    "imageMode": "sprite",
                    "spriteIndex": 1,
                    "imageGridCellSize": [16, 16],
                    "imageSize": [16, 16],
                    "imageRequired": True,
                },
            )
        ],
        tmp_path,
        tmp_path / "out",
    )
    assert result.errors == []
    assert result.entities[0].image_crop_rect == (16, 0, 16, 16)


def test_recipe_projection_emits_typed_materials_and_output_references(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "crafting_recipe:1",
                "crafting_recipe",
                extra_json={
                    "legacyFields": ["24 2 472 1"],
                    "outputItemId": "(O)100",
                },
            ),
            entity("object:24", "object"),
            entity("object:472", "object"),
            entity("object:100", "object"),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    output = next(
        fact for fact in package.fact_slots if fact.slot_key == "crafting_output_item_id"
    )
    assert output.text_value == "object:100"
    materials = [
        item for item in package.fact_items if item.slot_id.endswith("crafting_material_id")
    ]
    quantities = [
        item
        for item in package.fact_items
        if item.slot_id.endswith("crafting_material_quantity")
    ]
    assert [item.text_value for item in materials] == ["object:24", "object:472"]
    assert [item.integer_value for item in quantities] == [2, 1]
    assert [item.scope_id for item in materials] == [item.scope_id for item in quantities]


def test_monster_drop_projection_keeps_item_reference_and_chance_condition(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity("monster:Green-Slime", "monster"),
            entity("object:128", "object"),
            entity(
                "drop:Green-Slime:0",
                "drop",
                extra_json={"monsterId": "Green Slime", "itemId": "128", "chance": "0.25"},
            ),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    slot = next(slot for slot in package.fact_slots if slot.slot_key == "drops")
    item = next(item for item in package.fact_items if item.slot_id == slot.id)
    assert item.text_value == "object:128"
    assert item.condition_set_id is not None
    assert (
        next(
            term
            for term in package.condition_terms
            if term.condition_set_id == item.condition_set_id
        ).kind
        == "chance"
    )


def test_weapon_projection_derives_sale_price_from_official_runtime_rule(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "weapon:1",
                "weapon",
                extra_json={
                    "MinDamage": 8,
                    "MaxDamage": 15,
                    "Speed": 0,
                    "Precision": 1,
                    "Defense": 1,
                    "Type": 0,
                    "CritChance": 0.02,
                    "CritMultiplier": 3.0,
                },
            )
        ],
        tmp_path,
        game_version="1.6.15",
    )
    facts = {fact.slot_key: fact for fact in package.fact_slots}
    assert facts["sell_price"].integer_value == 300
    evidence = next(
        evidence
        for evidence in package.evidence
        if evidence.id.endswith(stable_part(facts["sell_price"].id))
    )
    assert evidence.transformation_rule == "official-weapon-sale-rule-to-player-facts-v1"


def test_weapon_projection_keeps_damage_and_explicit_purchase_semantics(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "weapon:1",
                "weapon",
                extra_json={
                    "MinDamage": 10,
                    "MaxDamage": 20,
                    "PurchasePrice": 500,
                    "Price": 50,
                },
            )
        ],
        tmp_path,
        game_version="1.6.15",
    )
    facts = {fact.slot_key: fact for fact in package.fact_slots}
    assert facts["damage_min"].integer_value == 10
    assert facts["damage_max"].integer_value == 20
    assert facts["purchase_price"].integer_value == 500
    assert facts["sell_price"].integer_value == 50


def test_weapon_acquisition_projection_keeps_shop_and_quest_provenance(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity("weapon:1", "weapon"),
            entity("weapon:13", "weapon"),
        ],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={
                "AdventureShop": {
                    "Currency": "Money",
                    "Items": [
                        {
                            "Id": "SilverSaber",
                            "ItemId": "(W)1",
                            "Price": 750,
                            "Condition": "MINE_LOWEST_LEVEL_REACHED 20",
                        }
                    ],
                }
            },
            monster_slayer_quests={
                "Insects": {
                    "RewardItemId": "(W)13",
                    "Count": 80,
                }
            },
        ),
    )
    acquisition = [
        item for item in package.fact_items if item.slot_id.endswith(":acquisition")
    ]
    weapon_one_items = [item for item in acquisition if item.slot_id == "fact:weapon:1:acquisition"]
    shop_item = next(item for item in weapon_one_items if item.text_value == "商店购买")
    quest_item = next(
        item
        for item in acquisition
        if item.slot_id == "fact:weapon:13:acquisition"
    )
    assert shop_item.condition_set_id is not None
    assert quest_item.text_value == "冒险家公会怪物猎杀任务奖励"
    assert quest_item.condition_set_id is None
    assert any(
        locator.source_file == "Data/Shops.json"
        and locator.record_key == "shop:AdventureShop:offer:SilverSaber"
        for locator in package.source_locators
    )
    quest_locator = next(
        locator
        for locator in package.source_locators
        if locator.source_file == "Data/MonsterSlayerQuests.json"
    )
    assert quest_locator.record_key == "Insects"


def test_weapon_dark_sword_has_haunted_skull_drop_rule(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [entity("weapon:2", "weapon")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(),
    )

    item = next(
        item
        for item in package.fact_items
        if item.slot_id == "fact:weapon:2:acquisition"
    )
    assert item.text_value == "闹鬼骷髅的诅咒娃娃变体随机掉落"
    condition = next(
        condition for condition in package.condition_sets if condition.id == item.condition_set_id
    )
    assert condition.completeness == "complete"
    assert "诅咒娃娃" in str(condition.player_summary)
    locator = next(
        locator
        for locator in package.source_locators
        if locator.id.endswith("Bat.getExtraDropItems")
    )
    assert locator.source_file == "Stardew Valley.dll"


def test_weapon_challenge_reward_rule_has_a_complete_condition(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [entity("weapon:61", "weapon")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(),
    )

    item = next(
        item
        for item in package.fact_items
        if item.slot_id == "fact:weapon:61:acquisition"
    )
    assert item.text_value == "挑战矿井额外难度奖励"
    condition = next(
        condition for condition in package.condition_sets if condition.id == item.condition_set_id
    )
    assert condition.completeness == "complete"
    assert condition.player_summary == "挑战矿井额外难度规则奖励"


def test_weapon_acquisition_projection_uses_explicit_game_rules_not_mine_level_fields(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [entity("weapon:16", "weapon")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(),
    )
    item = next(
        item
        for item in package.fact_items
        if item.slot_id == "fact:weapon:16:acquisition"
    )
    assert item.text_value == "矿井特殊掉落"
    assert item.condition_set_id is not None
    condition = next(
        condition for condition in package.condition_sets if condition.id == item.condition_set_id
    )
    assert condition.player_summary == "矿井第 1-19 层"
    locator = next(
        locator
        for locator in package.source_locators
        if locator.id
        == (
            "locator:official-rule:weapon-acquisition:"
            "MineShaft.getSpecialItemForThisMineLevel"
        )
    )
    assert locator.source_file == "Stardew Valley.dll"


def test_villager_support_records_aggregate_into_typed_fact_items(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [entity("villager:Abigail", "villager"), entity("object:24", "object")],
        tmp_path,
        game_version="1.6.15",
        support_entities=[
            entity(
                "npc_schedule:Abigail:Wed_6",
                "npc_schedule",
                extra_json={"time": "06:00", "location": "Town"},
            ),
            entity(
                "villager_gift:Abigail",
                "villager_gift",
                extra_json={
                    "GiftTastes": [
                        {"preference": "loved", "items": ["24", "category_fruits"]},
                        {"preference": "hated", "items": ["missing"]},
                    ]
                },
            ),
        ],
    )
    slots = {slot.slot_key: slot for slot in package.fact_slots}
    assert {"schedule", "gift_preferences"} <= slots.keys()
    assert {item.text_value for item in package.fact_items} >= {
        "时间：06:00；地点：Town",
        "object:24",
        "类别引用：fruits",
        "未解析礼物引用：missing",
    }
    assert any(":loved:" in (item.scope_id or "") for item in package.fact_items)
    assert any(":hated:" in (item.scope_id or "") for item in package.fact_items)
    assert all(
        claim.claim_id in {item.id for item in package.fact_items}
        for claim in package.claim_evidence
        if claim.claim_type == "fact_item"
    )


def test_villager_projection_keeps_residence_gender_and_relationship_semantics(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "villager:Abigail",
                "villager",
                extra_json={
                    "HomeRegion": "Town",
                    "Gender": "Female",
                    "CanBeRomanced": True,
                    "BirthSeason": "Fall",
                    "BirthDay": 13,
                    "LoveInterest": "Sebastian",
                },
            ),
            entity("villager:Sebastian", "villager"),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    facts = {fact.slot_key: fact for fact in package.fact_slots}
    assert facts["residence_region"].text_value == "Town"
    assert facts["gender"].text_value == "Female"
    assert facts["can_be_romanced"].boolean_value is True
    assert facts["birthday"].text_value == "Fall 13"
    assert package.relations[0].predicate == "love_interest_pointer"
    assert package.relations[0].object_entity_id == "villager:Sebastian"


def test_fish_projection_emits_typed_core_fields_and_sell_price(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "fish:128",
                "fish",
                extra_json={
                    "legacyFields": [
                        "Pufferfish",
                        "80",
                        "floater",
                        "1",
                        "36",
                        "1200 1600",
                        "summer",
                        "sunny",
                    ]
                },
            ),
            entity("object:128", "object", extra_json={"Price": 200}),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    facts = {fact.slot_key: fact for fact in package.fact_slots}
    assert facts["difficulty"].integer_value == 80
    assert facts["behavior"].text_value == "floater"
    assert facts["fishing_time"].text_value == "1200 1600"
    assert facts["seasons"].text_value == "summer"
    assert facts["weather"].text_value == "sunny"
    assert facts["sell_price"].integer_value == 200


def test_mine_fish_support_projection_emits_depth_bands_and_dll_locator(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity("fish:158", "fish"),
            entity("fish:161", "fish"),
            entity("fish:162", "fish"),
        ],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(),
    )
    location_items = [
        item for item in package.fact_items if item.slot_id.endswith(":fishing_locations")
    ]
    assert {item.slot_id.split(":fishing_locations", 1)[0] for item in location_items} >= {
        "fact:fish:158",
        "fact:fish:161",
        "fact:fish:162",
    }
    stonefish = next(
        item for item in package.fact_items if item.id.startswith("fact-item:fish:158:")
    )
    assert stonefish.text_value == "Mine"
    assert stonefish.condition_set_id is not None
    condition = next(c for c in package.condition_sets if c.id == stonefish.condition_set_id)
    assert "矿井起始层：1" in (condition.player_summary or "")
    assert "矿井结束层：10" in (condition.player_summary or "")
    locator_id = next(
        evidence.source_locator_id
        for evidence in package.evidence
        if evidence.id.endswith(stable_part(stonefish.id))
    )
    locator = next(locator for locator in package.source_locators if locator.id == locator_id)
    assert locator.source_file == "Stardew Valley.dll"
    assert locator.record_key == "StardewValley.Locations.MineShaft.getFish"
    assert locator.json_path is None
    validate_schema5_package(package, publishable=True)


def test_fish_support_projection_emits_stable_scoped_location_and_condition(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [entity("fish:128", "fish")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            locations={
                "Beach": {
                    "Fish": [
                        {
                            "ItemId": "(O)128",
                            "Season": "Spring",
                            "Chance": 0.2,
                            "MinFishingLevel": 2,
                        }
                    ]
                }
            }
        ),
    )
    slot = next(slot for slot in package.fact_slots if slot.slot_key == "fishing_locations")
    item = package.fact_items[0]
    assert item.id.startswith("fact-item:fish:128:fishing_locations:Beach%7C")
    assert item.scope_id.startswith("fishing:fish:128:Beach%7C")
    assert item.condition_set_id is not None
    fishing_facet = next(
        facet for facet in package.facets if facet.scope_family == "fishing_location"
    )
    assert fishing_facet.text_value == "Beach"
    assert fishing_facet.scope_id == item.scope_id
    card = next(card for card in package.entity_cards if card.entity_id == "fish:128")
    assert card.action_summary_1 == "地点：Beach"
    condition = next(
        condition for condition in package.condition_sets if condition.id == item.condition_set_id
    )
    assert condition.completeness == "complete"
    assert "季节：Spring" in (condition.player_summary or "")
    assert {term.kind for term in package.condition_terms} == {
        "season",
        "chance",
        "minFishingLevel",
    }
    validate_schema5_package(package, publishable=True)
    paths = write_schema5_package(tmp_path, package, game_version="1.6.15")
    with sqlite3.connect(paths["database"]) as connection:
        assert connection.execute(
            "SELECT condition_set_id FROM fact_items WHERE slot_id = ?", (slot.id,)
        ).fetchone() == (item.condition_set_id,)


def test_monster_support_projection_emits_typed_location_and_locator(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [entity("monster:Green-Slime", "monster")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            locations={
                "Mines": {
                    "Monsters": [{"Id": "Green Slime"}],
                }
            }
        ),
    )
    item = next(item for item in package.fact_items if item.slot_id.endswith(":locations"))
    assert item.text_value == "Mines"
    assert item.scope_id.startswith("monster-location:monster:Green-Slime:")
    locator = next(locator for locator in package.source_locators if locator.id == next(
        evidence.source_locator_id
        for evidence in package.evidence
        if evidence.id.endswith(stable_part(item.id))
    ))
    assert locator.source_file == "Data/Locations.json"
    assert locator.json_path == "$.Mines.Monsters[*]"
    assert any(facet.scope_family == "monster_location" for facet in package.facets)
    validate_schema5_package(package, publishable=True)


def test_machine_and_recipe_usage_support_rows_keep_scope_and_typed_values(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity("object:24", "object"),
            entity("big_craftable:FishSmoker", "big_craftable"),
            entity(
                "crafting_recipe:Wood",
                "crafting_recipe",
                extra_json={"legacyFields": ["24 2"]},
            ),
        ],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            machines={
                "(BC)FishSmoker": {
                    "OutputRules": [
                        {
                            "Id": "smoke",
                            "Triggers": [
                                {
                                    "Id": "parsnip",
                                    "RequiredItemId": "24",
                                    "RequiredCount": 2,
                                }
                            ],
                            "MinutesUntilReady": 50,
                        }
                    ]
                }
            }
        ),
    )
    machine_item = next(
        item
        for item in package.fact_items
        if item.slot_id == "fact:object:24:machine_uses"
    )
    assert machine_item.text_value == "big_craftable:FishSmoker"
    assert machine_item.scope_id == "machine:%28BC%29FishSmoker:smoke:parsnip"
    assert next(
        item
        for item in package.fact_items
        if item.slot_id == "fact:object:24:machine_use_required_count"
    ).integer_value == 2
    usage_item = next(
        item for item in package.fact_items if item.slot_id == "fact:object:24:used_in"
    )
    assert usage_item.text_value == "crafting_recipe:Wood"
    assert usage_item.scope_id == "usage:crafting_recipe:Wood"
    assert next(
        item
        for item in package.fact_items
        if item.slot_id == "fact:object:24:used_in_quantity"
    ).integer_value == 2


def test_shop_projection_emits_purchase_and_seed_offer_facts(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity("object:472", "object"),
            entity("crop:472", "crop", extra_json={"SeedItemId": "472"}),
        ],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={
                "SeedShop": {
                    "Currency": "Money",
                    "Items": [
                        {
                            "Id": "parsnip-seeds",
                            "ItemId": "(O)472",
                            "Price": 20,
                            "Condition": "SEASON spring",
                        }
                    ],
                }
            }
        ),
    )
    object_price = next(
        item
        for item in package.fact_items
        if item.slot_id == "fact:object:472:purchase_price"
    )
    crop_price = next(
        item
        for item in package.fact_items
        if item.slot_id == "fact:crop:472:seed_purchase_price"
    )
    assert object_price.integer_value == 20
    assert crop_price.integer_value == 20
    assert any(
        facet.scope_family == "purchase_price" and facet.integer_value == 20
        for facet in package.facets
    )
    assert any(
        facet.scope_family == "seed_purchase_price" and facet.integer_value == 20
        for facet in package.facets
    )
    assert object_price.scope_id == crop_price.scope_id == "offer:shop:SeedShop:offer:parsnip-seeds"
    assert object_price.condition_set_id is not None
    condition = next(
        condition
        for condition in package.condition_sets
        if condition.id == object_price.condition_set_id
    )
    assert condition.completeness == "opaque"
    assert "商店报价受游戏条件或价格规则限制" == condition.player_summary
    assert any(
        item.slot_id == "fact:object:472:purchase_currency"
        and item.text_value == "金币"
        for item in package.fact_items
    )
    locator = next(
        locator
        for locator in package.source_locators
        if locator.source_document_id == "source:official-support:shops"
    )
    assert locator.json_path == "$.SeedShop.Items[*]"
    write_schema5_package(tmp_path, package, game_version="1.6.15")


def test_shop_exchange_offer_keeps_cost_separate_from_coin_price(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [entity("big_craftable:248", "big_craftable"), entity("object:858", "object")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={
                "QiGemShop": {
                    "Currency": 4,
                    "Items": [
                        {
                            "ItemId": "(BC)248",
                            "Price": -1,
                            "TradeItemId": "(O)858",
                            "TradeItemAmount": 60,
                        }
                    ],
                }
            }
        ),
    )
    assert not any(
        item.slot_id == "fact:big_craftable:248:purchase_price"
        for item in package.fact_items
    )
    assert any(
        item.slot_id == "fact:big_craftable:248:purchase_currency"
        and item.text_value == "齐钻"
        for item in package.fact_items
    )
    assert any(
        item.slot_id == "fact:big_craftable:248:purchase_exchange_item_id"
        and item.text_value == "object:858"
        for item in package.fact_items
    )
    assert any(
        item.slot_id == "fact:big_craftable:248:purchase_exchange_amount"
        and item.integer_value == 60
        for item in package.fact_items
    )


def test_crop_projection_derives_harvest_sell_price_from_typed_object_input(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "crop:24",
                "crop",
                extra_json={"HarvestItemId": "24"},
            ),
            entity("object:24", "object", extra_json={"Price": 35}),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    sell_price = next(
        fact for fact in package.fact_slots if fact.id == "fact:crop:24:sell_price"
    )
    assert sell_price.integer_value == 35
    evidence = next(
        evidence
        for evidence in package.evidence
        if evidence.id == "evidence:fact:fact:crop:24:sell_price"
    )
    assert evidence.input_claim_id == "object:24"
    assert evidence.transformation_rule == "official-crop-harvest-to-player-facts-v1"


def test_crop_projection_emits_typed_core_slots(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "crop:24",
                "crop",
                extra_json={
                    "Seasons": ["Spring"],
                    "DaysInPhase": [1, 1, 1, 1],
                    "RegrowDays": -1,
                    "NeedsWatering": True,
                    "SeedItemId": "472",
                    "HarvestItemId": "24",
                },
            ),
            entity("object:472", "object"),
            entity("object:24", "object"),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    facts = {fact.slot_key: fact for fact in package.fact_slots}
    assert facts["seasons"].text_value == "Spring"
    assert facts["first_harvest_days"].integer_value == 4
    assert facts["regrow_days"].status == "not_applicable"
    assert facts["needs_watering"].boolean_value is True
    assert facts["seed_item_id"].text_value == "object:472"
    assert facts["harvest_item_id"].text_value == "object:24"
    assert [
        facet.text_value for facet in package.facets if facet.scope_family == "season"
    ] == ["春季"]
    assert {claim.claim_id for claim in package.claim_evidence} >= {
        fact.id for fact in package.fact_slots
    }
    derived_evidence = next(
        evidence
        for evidence in package.evidence
        if evidence.id.startswith("evidence:fact:")
    )
    assert derived_evidence.input_claim_id == "crop:24"


def test_projection_uses_materialized_rect_and_marks_unresolved_relationship_unknown(
    tmp_path: Path,
) -> None:
    image = tmp_path / "images" / "villager-abigail.webp"
    image.parent.mkdir()
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(image)
    abigail = entity(
        "villager:Abigail",
        "villager",
        image_path="images/villager-abigail.webp",
        image_crop_rect=(0, 0, 16, 16),
        extra_json={
            "FriendsAndFamily": {
                "Caroline": "[LocalizedText Strings\\Characters:Relative_Mom]",
                "MissingNpc": "",
            },
            "CanBeRomanced": True,
            "BirthSeason": "Fall",
            "BirthDay": 13,
        },
    )
    caroline = entity("villager:Caroline", "villager")
    package = build_schema5_staging_package(
        [abigail, caroline], tmp_path, game_version="1.6.15"
    )
    groups = {(group.family, group.status) for group in package.relation_groups}
    assert ("friendship", "unknown") in groups
    assert ("kinship", "fixed") in groups
    assert {(relation.predicate, relation.object_entity_id) for relation in package.relations} == {
        ("kinship", "villager:Caroline")
    }
    assert package.visuals[0].crop_rect == "[0,0,16,16]"
    assert all(relation.predicate != "love_interest_pointer" for relation in package.relations)


def test_mixed_family_relationships_use_distinct_groups_and_ids(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "villager:Abigail",
                "villager",
                extra_json={
                    "FriendsAndFamily": {
                        "Caroline": "[LocalizedText Strings\\Characters:Relative_Mom]",
                        "Sebastian": "[LocalizedText Strings\\Characters:Friend]",
                    }
                },
            ),
            entity("villager:Caroline", "villager"),
            entity("villager:Sebastian", "villager"),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    assert {(group.family, group.status) for group in package.relation_groups} == {
        ("friendship", "fixed"),
        ("kinship", "fixed"),
    }
    assert {(relation.predicate, relation.object_entity_id) for relation in package.relations} == {
        ("friendship", "villager:Sebastian"),
        ("kinship", "villager:Caroline"),
    }
    assert {relation.relation_group_id for relation in package.relations} == {
        "group:villager:Abigail:friendship",
        "group:villager:Abigail:kinship",
    }


def test_partial_relationships_are_unknown_without_edges_at_write_boundary(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "villager:Abigail",
                "villager",
                extra_json={
                    "FriendsAndFamily": {"MissingNpc": ""},
                    "LoveInterest": "MissingNpc",
                },
            )
        ],
        tmp_path,
        game_version="1.6.15",
    )
    assert all(group.status == "unknown" for group in package.relation_groups)
    assert package.relations == []
    write_schema5_package(tmp_path, package, publishable=False)


def test_projection_marks_gift_visual_as_official_reuse_only_for_explicit_gift(
    tmp_path: Path,
) -> None:
    image = tmp_path / "images" / "gift.webp"
    image.parent.mkdir()
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(image)
    package = build_schema5_staging_package(
        [
            entity("villager:Abigail", "villager"),
            entity(
                "villager_gift:Abigail",
                "villager_gift",
                image_path="images/gift.webp",
                image_crop_rect=(0, 0, 16, 16),
                extra_json={"imageRequired": False},
            ),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    visuals = {visual.entity_id: visual for visual in package.visuals}
    assert visuals["villager_gift:Abigail"].status == "official_reuse"
    assert visuals["villager:Abigail"].status == "official_none"


def test_real_staging_conformance_is_not_labelled_fixture(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [entity("object:1", "object")], tmp_path, game_version="1.6.15"
    )
    paths = write_schema5_package(
        tmp_path, package, game_version="1.6.15", publishable=False
    )
    import json

    assert json.loads(paths["conformance"].read_text(encoding="utf-8"))["status"] == "staging"


def test_schema5_writer_commit_failure_preserves_existing_protocol_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from builder.pipeline import schema5_writer

    package = build_schema5_staging_package(
        [entity("object:1", "object")], tmp_path, game_version="1.6.15"
    )
    database = tmp_path / "stardew.db"
    manifest = tmp_path / "manifest.json"
    conformance = tmp_path / "schema5-conformance.json"
    database.write_bytes(b"old-database")
    manifest.write_text("old-manifest", encoding="utf-8")
    conformance.write_text("old-conformance", encoding="utf-8")

    def fail_commit(files: object) -> None:
        raise OSError("commit failure")

    monkeypatch.setattr(schema5_writer, "commit_schema5_files", fail_commit)
    with pytest.raises(OSError, match="commit failure"):
        write_schema5_package(tmp_path, package, game_version="1.6.15")
    assert database.read_bytes() == b"old-database"
    assert manifest.read_text(encoding="utf-8") == "old-manifest"
    assert conformance.read_text(encoding="utf-8") == "old-conformance"


def test_written_staging_fixture_has_schema5_integrity(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [entity("object:1", "object")], tmp_path, game_version="1.6.15"
    )
    paths = write_schema5_package(tmp_path, package, publishable=False)
    with sqlite3.connect(paths["database"]) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_block_release_creates_marker_for_new_output(tmp_path: Path) -> None:
    output = tmp_path / "new-output"
    block_release(output, "failed")
    assert (output / ".release-blocked.json").is_file()


def test_staging_command_failure_keeps_old_output_and_blocks_it(tmp_path: Path) -> None:
    from builder.commands import schema5_staging

    output = tmp_path / "staging"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("old", encoding="utf-8")
    original_loader = schema5_staging.load_game_data_from_unpacked_dir
    original_resolver = schema5_staging.resolve_build_inputs

    def fail_loader(path: Path) -> object:
        raise ValueError("source failure")

    def resolve_inputs(*args: object, **kwargs: object) -> tuple[Path, Path, str]:
        return tmp_path, tmp_path, "explicit"

    schema5_staging.load_game_data_from_unpacked_dir = fail_loader
    schema5_staging.resolve_build_inputs = resolve_inputs
    try:
        with pytest.raises(ValueError, match="source failure"):
            schema5_staging.build_schema5_staging_command(
                str(tmp_path), str(output), str(tmp_path)
            )
    finally:
        schema5_staging.load_game_data_from_unpacked_dir = original_loader
        schema5_staging.resolve_build_inputs = original_resolver
    assert sentinel.read_text(encoding="utf-8") == "old"
    assert (output / ".release-blocked.json").is_file()


def test_projection_rejects_sprite_without_materialized_rect(tmp_path: Path) -> None:
    image = tmp_path / "images" / "object.webp"
    image.parent.mkdir()
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(image)
    with pytest.raises(ValueError, match="物化裁切矩形"):
        build_schema5_staging_package(
            [
                entity(
                    "object:1",
                    "object",
                    image_path="images/object.webp",
                    extra_json={"spriteIndex": 1},
                )
            ],
            tmp_path,
            game_version="1.6.15",
        )


def test_writer_rejects_invalid_crop_rect(tmp_path: Path) -> None:
    image = tmp_path / "images" / "object.webp"
    image.parent.mkdir()
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(image)
    package = build_schema5_staging_package(
        [
            entity(
                "object:1",
                "object",
                image_path="images/object.webp",
                image_crop_rect=(0, 0, 16, 16),
            )
        ],
        tmp_path,
        game_version="1.6.15",
    )
    package.visuals[0] = package.visuals[0].__class__(
        **{**package.visuals[0].__dict__, "crop_rect": "garbage"}
    )
    with pytest.raises(ValueError, match="裁切矩形"):
        write_schema5_package(tmp_path, package, publishable=False)


def test_projection_rejects_required_image_without_materialized_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="必需视觉"):
        build_schema5_staging_package(
            [entity("object:1", "object", extra_json={"imageRequired": True})],
            tmp_path,
            game_version="1.6.15",
        )
