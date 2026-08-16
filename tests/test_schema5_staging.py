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


def test_runtime_monster_location_uses_auditable_conditional_rule(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [entity("monster:Lava-Lurk", "monster")],
        tmp_path,
        game_version="1.6.15.24356",
        support=OfficialSupportData(),
        official_release_binding=(
            "7f1e5b8e58d2758b78570ba771bbeb03d33522f62188bf6c32edf0cf626deaee",
            "fixture-assets",
        ),
    )

    slot = next(
        slot for slot in package.fact_slots if slot.id == "fact:monster:Lava-Lurk:locations"
    )
    assert slot.status == "conditional"
    item = next(item for item in package.fact_items if item.slot_id == slot.id)
    assert item.text_value == "火山地牢"
    condition = next(
        condition for condition in package.condition_sets if condition.id == item.condition_set_id
    )
    assert condition.completeness == "partial"
    assert "熔岩区" in str(condition.player_summary)
    locator = next(
        locator
        for locator in package.source_locators
        if locator.id.endswith("VolcanoDungeon.GenerateEntities")
    )
    assert locator.source_file == "Stardew Valley.dll"


def test_game_state_query_rejects_incomplete_or_malformed_predicates() -> None:
    from builder.pipeline.schema5_projection import game_state_query_terms

    assert game_state_query_terms("condition:test", "SEASON", 0)[2] is False
    assert game_state_query_terms("condition:test", "PLAYER_HEARTS Alex", 0)[2] is False
    assert game_state_query_terms("condition:test", 'ANY "SEASON spring', 0)[2] is False
    assert game_state_query_terms("condition:test", 'ANY "SEASON spring" "YEAR 2"', 0)[2] is False
    assert game_state_query_terms("condition:test", "SEASON spring unexpected", 0)[2] is False
    assert (
        game_state_query_terms(
            "condition:test", "IS_COMMUNITY_CENTER_COMPLETE unexpected", 0
        )[2]
        is False
    )
    assert game_state_query_terms("condition:test", "YEAR not-a-number", 0)[2] is False


def test_nonspawnable_legacy_monster_location_is_not_applicable(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [entity("monster:Crow", "monster")],
        tmp_path,
        game_version="1.6.15.24356",
        support=OfficialSupportData(),
        official_release_binding=(
            "7f1e5b8e58d2758b78570ba771bbeb03d33522f62188bf6c32edf0cf626deaee",
            "fixture-assets",
        ),
    )

    slot = next(slot for slot in package.fact_slots if slot.id == "fact:monster:Crow:locations")
    assert slot.status == "not_applicable"
    assert not any(item.slot_id == slot.id for item in package.fact_items)
    drops = next(slot for slot in package.fact_slots if slot.id == "fact:monster:Crow:drops")
    assert drops.status == "not_applicable"


def test_noncombat_monster_ignores_legacy_drop_record(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity("monster:Crow", "monster"),
            entity("object:1", "object"),
            entity(
                "drop:Crow:0",
                "drop",
                extra_json={"monsterId": "Crow", "itemId": "1", "chance": "0.5"},
            ),
        ],
        tmp_path,
        game_version="1.6.15.24356",
        support=OfficialSupportData(),
        official_release_binding=(
            "7f1e5b8e58d2758b78570ba771bbeb03d33522f62188bf6c32edf0cf626deaee",
            "fixture-assets",
        ),
    )
    slot = next(slot for slot in package.fact_slots if slot.id == "fact:monster:Crow:drops")
    assert slot.status == "not_applicable"
    assert not any(item.slot_id == slot.id for item in package.fact_items)


def test_unobtainable_weapon_policy_is_exact_release_bound(tmp_path: Path) -> None:
    weapon = entity("weapon:34", "weapon")
    bound = build_schema5_staging_package(
        [weapon],
        tmp_path,
        game_version="1.6.15.24356",
        support=OfficialSupportData(),
        official_release_binding=(
            "7f1e5b8e58d2758b78570ba771bbeb03d33522f62188bf6c32edf0cf626deaee",
            "d582dd6b3e9260eee2f26c00d16a14704e4ef44a3d2cf0a4de94f9375c356222",
        ),
    )
    slot = next(slot for slot in bound.fact_slots if slot.id == "fact:weapon:34:acquisition")
    assert slot.status == "not_applicable"
    assert any(
        evidence.transformation_rule == "official-current-version-unobtainable-weapon-v1"
        for evidence in bound.evidence
    )

    changed_asset = build_schema5_staging_package(
        [weapon],
        tmp_path,
        game_version="1.6.15.24356",
        support=OfficialSupportData(),
        official_release_binding=("different-dll", "different-assets"),
    )
    assert not any(
        slot.id == "fact:weapon:34:acquisition" for slot in changed_asset.fact_slots
    )


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


def test_ginger_island_event_projects_trigger_condition_fact(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "ginger_island:IslandSouth:6497428/e-6497423/f-Leo-1500/w-sunny/t-600-1800/Hl-leoMoved",
                "ginger_island",
            ),
            entity(
                "ginger_island:IslandNorth:6497421/e 6497423/f Leo 1000/w sunny/t 600 1800/Hl leoMoved",
                "ginger_island",
            ),
            entity("ginger_island:IslandDepart", "ginger_island"),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    slots = [
        slot
        for slot in package.fact_slots
        if slot.slot_key == "ginger_trigger_condition"
    ]
    assert len(slots) == 2
    assert all(slot.text_value == "天气：晴天，时间：6:00–18:00" for slot in slots)
    assert not any(
        slot.slot_key == "ginger_trigger_condition"
        for slot in package.fact_slots
        if slot.entity_id.endswith("IslandDepart")
    )


def test_food_object_projects_edibility_and_buff_facts(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "object:206",
                "object",
                extra_json={
                    "Edibility": 60,
                    "Buffs": [
                        {
                            "Id": "Food",
                            "Duration": 480,
                            "CustomAttributes": {
                                "FarmingLevel": 3.0,
                                "Speed": 0.0,
                                "Defense": 1.0,
                            },
                        }
                    ],
                },
            ),
            entity("object:434", "object", extra_json={"Edibility": 100}),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    facts = {fact.slot_key: fact for fact in package.fact_slots}
    pizza = next(
        fact
        for fact in package.fact_slots
        if fact.entity_id == "object:206" and fact.slot_key == "edibility"
    )
    assert pizza.text_value == "恢复 150 体力、恢复 67 生命"
    assert facts["food_buffs"].text_value == "耕种+3、防御+1（持续 8 小时）"
    stardrop = next(
        fact
        for fact in package.fact_slots
        if fact.entity_id == "object:434" and fact.slot_key == "edibility"
    )
    assert stardrop.text_value == "恢复全部体力"


def test_bundle_projects_reward_fact_with_chinese_name(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "bundle:0",
                "bundle",
                extra_json={
                    "BundleRewards": [
                        {"type": "O", "itemId": "465", "quantity": 20},
                        {"type": "BO", "itemId": "10", "quantity": 1},
                    ]
                },
            ),
            NormalizedEntity(
                id="object:465",
                entity_type="object",
                game_id="465",
                internal_name=None,
                name_zh="生长激素",
                name_en=None,
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={},
                source_file="Data/Objects.json",
            ),
            NormalizedEntity(
                id="big_craftable:10",
                entity_type="big_craftable",
                game_id="10",
                internal_name=None,
                name_zh="蜂房",
                name_en=None,
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={},
                source_file="Data/BigCraftables.json",
            ),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    slot = next(slot for slot in package.fact_slots if slot.slot_key == "bundle_reward")
    assert slot.text_value == "生长激素×20、蜂房"


def test_vault_bundle_gold_ingredient_label(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "bundle:Vault/25",
                "bundle",
                extra_json={
                    "BundleIngredients": [
                        {"itemId": "-1", "quantity": 10000, "quality": 10000}
                    ]
                },
            )
        ],
        tmp_path,
        game_version="1.6.15",
    )
    slot = next(
        slot for slot in package.fact_slots if slot.slot_key == "bundle_ingredients"
    )
    assert slot.text_value == "10000 金币"


def test_item_projects_gift_likers_and_drop_sources(tmp_path: Path) -> None:
    def named(entity_id: str, entity_type: str, name_zh: str, extra: dict[str, object] | None = None) -> NormalizedEntity:
        return NormalizedEntity(
            id=entity_id,
            entity_type=entity_type,
            game_id=entity_id.split(":", 1)[1],
            internal_name=None,
            name_zh=name_zh,
            name_en=None,
            description_zh=None,
            description_en=None,
            category=None,
            image_path=None,
            image_crop_rect=None,
            extra_json=extra or {},
            source_file="Data/Characters.json",
        )

    package = build_schema5_staging_package(
        [
            named("villager:Abigail", "villager", "阿比盖尔"),
            named(
                "villager_gift:Abigail",
                "villager_gift",
                "阿比盖尔的礼物偏好",
                {
                    "GiftTastes": [
                        {"preference": "loved", "items": ["66", "74"]},
                        {"preference": "liked", "items": ["130"]},
                    ]
                },
            ),
            named(
                "villager_gift:Universal_Love",
                "villager_gift",
                "通用礼物偏好：最爱",
                {"GiftTastes": [{"preference": "loved", "items": ["74"]}]},
            ),
            named("monster:Green-Slime", "monster", "绿色史莱姆"),
            named("object:66", "object", "紫水晶"),
            named("object:74", "object", "五彩碎片"),
            named(
                "drop:Green-Slime:0",
                "drop",
                "绿色史莱姆掉落：紫水晶（75%）",
                {"monsterId": "Green Slime", "itemId": "66", "chance": ".75"},
            ),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    by_entity: dict[str, dict[str, str]] = {}
    for fact in package.fact_slots:
        by_entity.setdefault(fact.entity_id, {})[fact.slot_key] = fact.text_value or ""

    assert by_entity["object:66"]["gift_likers"] == "最爱：阿比盖尔"
    assert by_entity["object:66"]["drop_sources"] == "绿色史莱姆（75%）"
    assert by_entity["object:74"]["gift_likers"] == "最爱：所有人"
    assert "drop_sources" not in by_entity.get("object:74", {})


def test_tv_date_label_matches_known_broadcast_dates() -> None:
    from builder.pipeline.schema5_projection import tv_date_label

    assert tv_date_label(3) == "奇数年春季21日"  # 萝卜沙拉
    assert tv_date_label(4) == "奇数年春季28日"  # 煎蛋卷
    assert tv_date_label(17) == "偶数年春季7日"  # 披萨


def test_recipe_sources_cover_tv_friendship_skill_and_shop(tmp_path: Path) -> None:
    support = OfficialSupportData(cooking_channel_episodes={"Pizza": 17})
    package = build_schema5_staging_package(
        [
            NormalizedEntity(
                id="cooking_recipe:Pizza",
                entity_type="cooking_recipe",
                game_id="Pizza",
                internal_name=None,
                name_zh="披萨",
                name_en="Pizza",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={"outputItemId": "206"},
                source_file="Data/CookingRecipes.json",
            ),
            NormalizedEntity(
                id="cooking_recipe:Salmon-Dinner",
                entity_type="cooking_recipe",
                game_id="Salmon Dinner",
                internal_name=None,
                name_zh="鲑鱼晚餐",
                name_en="Salmon Dinner",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={"UnlockCondition": "f Gus 3"},
                source_file="Data/CookingRecipes.json",
            ),
            NormalizedEntity(
                id="cooking_recipe:Lucky-Lunch",
                entity_type="cooking_recipe",
                game_id="Lucky Lunch",
                internal_name=None,
                name_zh="幸运午餐",
                name_en="Lucky Lunch",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={"UnlockCondition": "s Luck 8"},
                source_file="Data/CookingRecipes.json",
            ),
            NormalizedEntity(
                id="cooking_recipe:Triple-Shot-Espresso",
                entity_type="cooking_recipe",
                game_id="Triple Shot Espresso",
                internal_name=None,
                name_zh="三倍浓缩咖啡",
                name_en="Triple Shot Espresso",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={"outputItemId": "253"},
                source_file="Data/CookingRecipes.json",
            ),
            NormalizedEntity(
                id="cooking_recipe:Fried-Egg",
                entity_type="cooking_recipe",
                game_id="Fried Egg",
                internal_name=None,
                name_zh="煎鸡蛋",
                name_en="Fried Egg",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={"UnlockCondition": "default"},
                source_file="Data/CookingRecipes.json",
            ),
            NormalizedEntity(
                id="villager:Gus",
                entity_type="villager",
                game_id="Gus",
                internal_name=None,
                name_zh="格斯",
                name_en="Gus",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={},
                source_file="Data/Characters.json",
            ),
            NormalizedEntity(
                id="shop:Saloon",
                entity_type="shop",
                game_id="Saloon",
                internal_name=None,
                name_zh="星之果实餐吧",
                name_en="Saloon",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={
                    "Items": [{"ItemId": "(O)253", "Price": 5000, "IsRecipe": True}]
                },
                source_file="Data/Shops.json",
            ),
        ],
        tmp_path,
        game_version="1.6.15",
        support=support,
    )
    by_entity: dict[str, dict[str, str]] = {}
    for fact in package.fact_slots:
        by_entity.setdefault(fact.entity_id, {})[fact.slot_key] = fact.text_value or ""

    assert by_entity["cooking_recipe:Pizza"]["recipe_source"] == "女王的美食（偶数年春季7日）"
    assert (
        by_entity["cooking_recipe:Salmon-Dinner"]["recipe_source"]
        == "与格斯好感度3心（邮件获得）"
    )
    assert by_entity["cooking_recipe:Lucky-Lunch"]["recipe_source"] == "幸运等级 8"
    assert (
        by_entity["cooking_recipe:Triple-Shot-Espresso"]["recipe_source"]
        == "星之果实餐吧购买"
    )
    assert by_entity["cooking_recipe:Fried-Egg"]["recipe_source"] == "初始掌握"


def test_special_order_rewards_and_bundle_quality_and_fish_pond(tmp_path: Path) -> None:
    support = OfficialSupportData(
        fish_ponds=[
            {
                "Id": "Pufferfish",
                "RequiredTags": ["item_pufferfish"],
                "ProducedItems": [
                    {"ItemId": "(O)812", "RequiredPopulation": 3, "Chance": 0.2}
                ],
            }
        ]
    )
    package = build_schema5_staging_package(
        [
            NormalizedEntity(
                id="special_order:Clint",
                entity_type="special_order",
                game_id="Clint",
                internal_name=None,
                name_zh="洞穴巡查",
                name_en="Cave Patrol",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={
                    "Rewards": [
                        {"Type": "Money", "Data": {"Amount": "6000"}},
                        {"Type": "Object", "Data": {"Item": "72", "Amount": "5"}},
                        {"Type": "Friendship", "Data": {}},
                        {"Type": "Mail", "Data": {"MailReceived": "x"}},
                    ]
                },
                source_file="Data/SpecialOrders.json",
            ),
            NormalizedEntity(
                id="special_order:Caroline",
                entity_type="special_order",
                game_id="Caroline",
                internal_name=None,
                name_zh="岛屿食材",
                name_en="Island Ingredients",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={
                    "Rewards": [
                        {"Type": "Money", "Data": {"Amount": "{Crop:Price}", "Multiplier": "50"}}
                    ]
                },
                source_file="Data/SpecialOrders.json",
            ),
            NormalizedEntity(
                id="object:72",
                entity_type="object",
                game_id="72",
                internal_name=None,
                name_zh="钻石",
                name_en="Diamond",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={},
                source_file="Data/Objects.json",
            ),
            NormalizedEntity(
                id="bundle:Crafts-Room/13",
                entity_type="bundle",
                game_id="Crafts Room/13",
                internal_name=None,
                name_zh="春季采集",
                name_en=None,
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={
                    "BundleIngredients": [
                        {"itemId": "190", "quantity": 5, "quality": 2}
                    ]
                },
                source_file="Data/Bundles.json",
            ),
            NormalizedEntity(
                id="object:190",
                entity_type="object",
                game_id="190",
                internal_name=None,
                name_zh="防风草",
                name_en="Parsnip",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={},
                source_file="Data/Objects.json",
            ),
            NormalizedEntity(
                id="fish:128",
                entity_type="fish",
                game_id="128",
                internal_name=None,
                name_zh="河豚",
                name_en="Pufferfish",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={},
                source_file="Data/Fish.json",
            ),
            NormalizedEntity(
                id="object:128",
                entity_type="object",
                game_id="128",
                internal_name=None,
                name_zh="河豚",
                name_en="Pufferfish",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={"ContextTags": ["item_pufferfish"]},
                source_file="Data/Objects.json",
            ),
            NormalizedEntity(
                id="object:812",
                entity_type="object",
                game_id="812",
                internal_name=None,
                name_zh="罗非鱼",
                name_en="Tilapia",
                description_zh=None,
                description_en=None,
                category=None,
                image_path=None,
                image_crop_rect=None,
                extra_json={},
                source_file="Data/Objects.json",
            ),
        ],
        tmp_path,
        game_version="1.6.15",
        support=support,
    )
    by_entity: dict[str, dict[str, str]] = {}
    for fact in package.fact_slots:
        by_entity.setdefault(fact.entity_id, {})[fact.slot_key] = fact.text_value or ""

    assert (
        by_entity["special_order:Clint"]["special_order_reward"]
        == "6000 金币、钻石×5、好感度"
    )
    assert (
        by_entity["special_order:Caroline"]["special_order_reward"]
        == "金币（按目标价值的 50 倍）"
    )
    assert (
        by_entity["bundle:Crafts-Room/13"]["bundle_ingredients"] == "防风草×5（金星）"
    )
    assert by_entity["fish:128"]["fish_pond_outputs"] == "罗非鱼（3 条后，20%）"


def test_furniture_projects_kind_fact(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity("furniture:0", "furniture", extra_json={"furnitureType": "chair"}),
            entity(
                "furniture:1120", "furniture", extra_json={"furnitureType": "table"}
            ),
            entity(
                "furniture:1122",
                "furniture",
                extra_json={"furnitureType": "bed double"},
            ),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    by_entity: dict[str, dict[str, str]] = {}
    for fact in package.fact_slots:
        by_entity.setdefault(fact.entity_id, {})[fact.slot_key] = fact.text_value or ""

    assert by_entity["furniture:0"]["furniture_kind"] == "椅子"
    assert by_entity["furniture:1120"]["furniture_kind"] == "桌子"
    assert by_entity["furniture:1122"]["furniture_kind"] == "双人床"


def test_monster_xp_and_crop_harvest_quantity(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity(
                "monster:Green-Slime",
                "monster",
                extra_json={"monsterHealth": 24, "monsterDamage": 5, "monsterXp": 3},
            ),
            entity(
                "crop:481",
                "crop",
                extra_json={
                    "HarvestMinStack": 3,
                    "HarvestMaxStack": 3,
                    "HarvestItemId": "258",
                },
            ),
            entity(
                "crop:885",
                "crop",
                extra_json={
                    "HarvestMinStack": 4,
                    "HarvestMaxStack": 7,
                    "HarvestItemId": "771",
                },
            ),
            entity(
                "crop:433",
                "crop",
                extra_json={
                    "HarvestMinStack": 4,
                    "HarvestMaxStack": 1,
                    "HarvestItemId": "433",
                },
            ),
            entity(
                "crop:472",
                "crop",
                extra_json={
                    "HarvestMinStack": 1,
                    "HarvestMaxStack": 1,
                    "HarvestItemId": "24",
                },
            ),
        ],
        tmp_path,
        game_version="1.6.15",
    )
    by_entity: dict[str, dict[str, str]] = {}
    integers: dict[str, dict[str, int]] = {}
    for fact in package.fact_slots:
        by_entity.setdefault(fact.entity_id, {})[fact.slot_key] = fact.text_value or ""
        if fact.integer_value is not None:
            integers.setdefault(fact.entity_id, {})[fact.slot_key] = fact.integer_value

    assert integers["monster:Green-Slime"]["monster_xp"] == 3
    assert by_entity["crop:481"]["harvest_quantity"] == "每次收获 3 个"
    assert by_entity["crop:885"]["harvest_quantity"] == "每次收获 4–7 个"
    assert by_entity["crop:433"]["harvest_quantity"] == "每次收获 4 个"
    assert "harvest_quantity" not in by_entity.get("crop:472", {})


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


def test_weapon_meowmere_has_forest_pylon_event_rule(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [entity("weapon:65", "weapon")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(),
    )

    item = next(
        item
        for item in package.fact_items
        if item.slot_id == "fact:weapon:65:acquisition"
    )
    assert item.text_value == "森林传送柱事件奖励"
    condition = next(
        condition for condition in package.condition_sets if condition.id == item.condition_set_id
    )
    assert condition.completeness == "complete"
    assert "远方之石" in str(condition.player_summary)
    locator = next(
        locator
        for locator in package.source_locators
        if locator.id.endswith("GameLocation.performAction:ForestPylon")
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
                        {"preference": "hated", "items": ["24", "missing"]},
                    ]
                },
            ),
        ],
    )
    slots = {slot.slot_key: slot for slot in package.fact_slots}
    assert {"schedule", "gift_preferences"} <= slots.keys()
    assert {item.text_value for item in package.fact_items} >= {
        "时间：6:00；地点：鹈鹕镇",
        "object:24",
        "水果",
    }
    assert "missing" not in {item.text_value for item in package.fact_items}
    assert any(
        row["token"] == "missing" for row in package.gift_reference_diagnostics
    )
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
    facts = {
        fact.slot_key: fact
        for fact in package.fact_slots
        if fact.entity_id == "villager:Abigail"
    }
    assert facts["residence_region"].text_value == "鹈鹕镇"
    assert facts["gender"].text_value == "女性"
    assert facts["can_be_romanced"].boolean_value is True
    assert facts["birthday"].text_value == "秋季 13 日"
    assert any(
        slot.slot_key == "gender" and slot.status == "not_applicable"
        for slot in package.fact_slots
        if slot.entity_id == "villager:Sebastian"
    ), "未注明性别的村民应输出 not_applicable 性别槽"
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
    assert facts["behavior"].text_value == "漂浮型"
    assert facts["fishing_time"].text_value == "12:00–16:00"
    assert facts["seasons"].text_value == "夏季"
    assert facts["weather"].text_value == "晴天"
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
    assert stonefish.text_value == "矿井"
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
    assert fishing_facet.text_value == "海滩"
    assert fishing_facet.scope_id == item.scope_id
    card = next(card for card in package.entity_cards if card.entity_id == "fish:128")
    assert card.action_summary_1 == "地点：海滩"
    condition = next(
        condition for condition in package.condition_sets if condition.id == item.condition_set_id
    )
    assert condition.completeness == "complete"
    assert "季节：春季" in (condition.player_summary or "")
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
                "UndergroundMine": {
                    "Monsters": [{"Id": "Green Slime"}],
                }
            }
        ),
    )
    item = next(item for item in package.fact_items if item.slot_id.endswith(":locations"))
    assert item.text_value == "矿井"
    assert item.scope_id.startswith("monster-location:monster:Green-Slime:")
    locator = next(locator for locator in package.source_locators if locator.id == next(
        evidence.source_locator_id
        for evidence in package.evidence
        if evidence.id.endswith(stable_part(item.id))
    ))
    assert locator.source_file == "Data/Locations.json"
    assert locator.json_path == "$.UndergroundMine.Monsters[*]"
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
    assert condition.completeness == "complete"
    assert "季节：春季" == condition.player_summary
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
    assert facts["seasons"].text_value == "春季"
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
