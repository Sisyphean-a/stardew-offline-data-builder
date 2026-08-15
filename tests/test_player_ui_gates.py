"""R1 红色产品门禁（builder 侧）：玩家可读投影零技术泄露。

这些测试把 RECOVERY.md 的“玩家界面硬门禁”落到 schema 5 构建输出上。
在当前实现下它们必须失败，并且失败信息必须指出实体、槽和泄露值。
修复方向由 R2+ 实现，不得在本文件里通过放宽断言“转绿”。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

import pytest

from builder.models import NormalizedEntity
from builder.pipeline.schema5_projection import build_schema5_staging_package

# 全槽通用：未解析引用与官方/类别引用一律禁止
UNIVERSAL_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    ("未解析引用", re.compile(r"未解析")),
    ("官方分类引用", re.compile(r"官方分类引用")),
    ("类别引用", re.compile(r"类别引用")),
    (
        "原始游戏状态查询",
        re.compile(r"\b(SEASON|DAY_OF_WEEK|YEAR|DAYS_PLAYED|"
                   r"MINE_LOWEST_LEVEL_REACHED|LOCATION_SEASON)\b"),
    ),
]

# 礼物槽：实体引用必须能在包内解析；未解析 token 一律禁止进入玩家事实。
GIFT_RAW_REFERENCE: re.Pattern[str] = re.compile(r"^[a-z_]+:\d+$")

# 日程槽：不允许内部地点代号与 Strings 令牌
SCHEDULE_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    (
        "日程内部地点代号",
        re.compile(r"\b(SamHouse|JojaMart|CommunityCenter|SeedShop|Desert|Hospital|Beach|"
                   r"JoshHouse|SebastianRoom|Mountain|Saloon|Spa|Forest|Town)\b"),
    ),
    ("日程字符串令牌", re.compile(r'Strings\\\\')),
]

SEASONS_ZH = {"spring": "春季", "summer": "夏季", "fall": "秋季", "winter": "冬季"}


def entity(
    entity_id: str,
    entity_type: str,
    *,
    game_id: str | None = None,
    extra_json: dict[str, object] | None = None,
) -> NormalizedEntity:
    return NormalizedEntity(
        id=entity_id,
        entity_type=entity_type,
        game_id=game_id if game_id is not None else entity_id.split(":", 1)[-1],
        internal_name=None,
        name_zh=entity_id,
        name_en=None,
        description_zh=None,
        description_en=None,
        category=None,
        extra_json=extra_json or {},
        source_file="Data/Characters.json",
    )


def build_package(
    tmp_path: Path,
    entities: list[NormalizedEntity],
    *,
    support_entities: list[NormalizedEntity] | None = None,
    support: object | None = None,
    game_version: str = "1.6.15",
    official_release_binding: tuple[str, str] | None = None,
) -> object:
    return build_schema5_staging_package(
        entities,
        tmp_path,
        game_version=game_version,
        support=support,
        support_entities=support_entities,
        official_release_binding=official_release_binding,
    )


def slots_of(package, entity_id: str, slot_key: str) -> list[object]:
    return [s for s in package.fact_slots if s.entity_id == entity_id and s.slot_key == slot_key]


def items_of(package, slot_id: str) -> list[object]:
    return [i for i in package.fact_items if i.slot_id == slot_id]


def card_of(package, entity_id: str) -> object | None:
    for card in package.entity_cards:
        if card.entity_id == entity_id:
            return card
    return None


def villager_fixture(*, with_gift_tokens: bool = True) -> list[NormalizedEntity]:
    entities = [
        entity(
            "villager:Jodi",
            "villager",
            game_id="Jodi",
            extra_json={
                "BirthSeason": "Fall",
                "BirthDay": 11,
                "CanBeRomanced": False,
                "HomeRegion": "Town",
                "Gender": "Female",
            },
        ),
        entity("object:72", "object", game_id="72"),
    ]
    if with_gift_tokens:
        entities.append(
            entity(
                "villager_gift:Jodi",
                "villager_gift",
                game_id="Jodi",
                extra_json={
                    "GiftTastes": [
                        {"preference": "loved", "items": ["Oh,", "object:72"]},
                        {"preference": "hated", "items": ["Daffodil"]},
                    ]
                },
            )
        )
    return entities


def gift_support_fixture() -> list[NormalizedEntity]:
    return [
        entity(
            "villager_gift:Jodi",
            "villager_gift",
            game_id="Jodi",
            extra_json={
                "GiftTastes": [
                    {"preference": "loved", "items": ["Oh,", "object:72"]},
                    {"preference": "hated", "items": ["Daffodil"]},
                ]
            },
        )
    ]


# --- 玩家可读中文规范值（当前实现直接透传官方枚举，必须失败） ---


def test_villager_birthday_is_localized_chinese(tmp_path: Path) -> None:
    package = build_package(tmp_path, villager_fixture(with_gift_tokens=False))
    slot = slots_of(package, "villager:Jodi", "birthday")[0]
    assert slot.text_value == "秋季 11 日", (
        f"villager:Jodi / birthday 泄露未本地化枚举：{slot.text_value!r}，应为「秋季 11 日」"
    )


def test_villager_residence_region_is_localized_chinese(tmp_path: Path) -> None:
    package = build_package(tmp_path, villager_fixture(with_gift_tokens=False))
    slot = slots_of(package, "villager:Jodi", "residence_region")[0]
    assert slot.text_value == "鹈鹕镇", (
        f"villager:Jodi / residence_region 泄露未本地化枚举：{slot.text_value!r}，应为「鹈鹕镇」"
    )


def test_villager_gender_is_localized_chinese(tmp_path: Path) -> None:
    package = build_package(tmp_path, villager_fixture(with_gift_tokens=False))
    slot = slots_of(package, "villager:Jodi", "gender")[0]
    assert slot.text_value == "女性", (
        f"villager:Jodi / gender 泄露未本地化枚举：{slot.text_value!r}，应为「女性」"
    )


# --- 礼物引用：未解析 token 与原始实体引用必须为 0 ---


def test_gift_items_have_zero_unresolved_or_raw_references(tmp_path: Path) -> None:
    package = build_package(
        tmp_path,
        villager_fixture(with_gift_tokens=False),
        support_entities=gift_support_fixture(),
    )
    entity_ids = {entity.id for entity in package.entities}
    gift_slots = slots_of(package, "villager:Jodi", "gift_preferences")
    violations: list[str] = []
    for slot in gift_slots:
        for item in items_of(package, slot.id):
            value = item.text_value or ""
            for label, pattern in UNIVERSAL_FORBIDDEN:
                if pattern.search(value):
                    violations.append(
                        f"villager:Jodi / gift_preferences[{item.scope_id}] "
                        f"包含{label}：{value!r}"
                    )
            if GIFT_RAW_REFERENCE.fullmatch(value) and value not in entity_ids:
                violations.append(
                    f"villager:Jodi / gift_preferences[{item.scope_id}] "
                    f"引用无对应实体：{value!r}"
                )
    assert not violations, "；".join(violations[:12])
    dropped = [row["token"] for row in package.gift_reference_diagnostics]
    assert "Oh," in dropped, "未解析礼物 token 应被丢弃并记入构建诊断"
    assert "Daffodil" in dropped, "未解析礼物 token 应被丢弃并记入构建诊断"


# --- 行动摘要：村民代表卡必须有两组契约摘要（生日、常住地） ---


def test_villager_card_has_birthday_and_residence_action_summaries(tmp_path: Path) -> None:
    package = build_package(tmp_path, villager_fixture(with_gift_tokens=False))
    card = card_of(package, "villager:Jodi")
    assert card is not None
    summaries = (card.action_summary_1, card.action_summary_2)
    assert all(summaries), (
        f"villager:Jodi 卡片缺少行动摘要：{summaries!r}；"
        f"契约要求生日与常住地各占一组（决策 04/10）"
    )
    joined = " ".join(s for s in summaries if s)
    assert "生日" in joined and "鹈鹕镇" in joined, (
        f"villager:Jodi 行动摘要未覆盖契约槽：{summaries!r}"
    )


# --- 日程：不泄露内部地点代号与 Strings 令牌 ---


def test_schedule_items_do_not_leak_internal_codes(tmp_path: Path) -> None:
    support = [
        entity(
            "npc_schedule:Jodi:spring",
            "npc_schedule",
            game_id="Jodi:spring",
            extra_json={
                "ScheduleEntries": [
                    {"time": 800, "location": "SamHouse", "route": [6, 5, 0, "jodi_dishes"]},
                    {"time": 2100, "location": "SamHouse", "route": [10, 22, 3]},
                ]
            },
        )
    ]
    package = build_package(
        tmp_path,
        villager_fixture(with_gift_tokens=False),
        support_entities=support,
    )
    schedule_slots = slots_of(package, "villager:Jodi", "schedule")
    violations: list[str] = []
    for slot in schedule_slots:
        for item in items_of(package, slot.id):
            value = item.text_value or ""
            for label, pattern in [*UNIVERSAL_FORBIDDEN, *SCHEDULE_FORBIDDEN]:
                if pattern.search(value):
                    violations.append(
                        f"villager:Jodi / schedule[{item.scope_id}] 包含{label}：{value!r}"
                    )
    assert not violations, "；".join(violations[:12])


# --- 作物：季节本地化 + 卡片行动摘要（季节/成熟，契约顺序） ---


def test_crop_seasons_are_localized_and_card_actions_follow_contract(tmp_path: Path) -> None:
    package = build_package(
        tmp_path,
        [
            entity(
                "crop:24",
                "crop",
                game_id="24",
                extra_json={
                    "Seasons": ["Spring"],
                    "DaysInPhase": [1, 1, 1, 1],
                    "RegrowDays": -1,
                    "NeedsWatering": True,
                    "SeedItemId": "472",
                    "HarvestItemId": "24",
                },
            ),
            entity("object:472", "object", game_id="472"),
            entity("object:24", "object", game_id="24"),
        ],
    )
    slot = slots_of(package, "crop:24", "seasons")[0]
    assert slot.text_value == "春季", (
        f"crop:24 / seasons 泄露未本地化枚举：{slot.text_value!r}，应为「春季」"
    )
    card = card_of(package, "crop:24")
    assert card is not None
    assert card.action_summary_1 == "季节：春季", f"作物卡片摘要顺序错误：{card.action_summary_1!r}"
    assert card.action_summary_2 == "成熟：4 天", f"作物卡片缺少成熟摘要：{card.action_summary_2!r}"


# --- 商店：地点/营业规则/店主/商品报价（中文 + 证据化） ---


def test_shop_projection_emits_localized_profile_and_quotes(tmp_path: Path) -> None:
    from builder.sources.official_support import OfficialSupportData

    package = build_package(
        tmp_path,
        [
            entity("shop:SeedShop", "shop", game_id="SeedShop"),
            NormalizedEntity(
                id="villager:Pierre",
                entity_type="villager",
                game_id="Pierre",
                internal_name=None,
                name_zh="皮埃尔",
                name_en="Pierre",
                description_zh=None,
                description_en=None,
                category=None,
                extra_json={
                    "BirthSeason": "Spring", "BirthDay": 26, "CanBeRomanced": False,
                    "HomeRegion": "Town", "Gender": "Male",
                },
                source_file="Data/Characters.json",
            ),
            entity("object:472", "object", game_id="472"),
        ],
        support=OfficialSupportData(
            shops={
                "SeedShop": {
                    "Currency": 0,
                    "Owners": [{"Name": "Pierre"}],
                    "Items": [
                        {"Id": "parsnip-seeds", "ItemId": "472", "Price": 20},
                    ],
                }
            }
        ),
    )
    slots = {
        slot.slot_key: slot for slot in package.fact_slots
        if slot.entity_id == "shop:SeedShop"
    }
    item_text = {
        (item.slot_id, item.scope_id): item.text_value for item in package.fact_items
    }
    def slot_text(slot_key: str) -> str | None:
        return next(
            (
                value
                for (slot_id, _), value in item_text.items()
                if slot_id == f"fact:shop:SeedShop:{slot_key}"
            ),
            None,
        )

    assert slot_text("location") == "皮埃尔杂货店", slot_text("location")
    assert slot_text("opening_hours") == "随店主日程变化"
    assert slots["opening_hours"].status == "dynamic_rule"
    assert slot_text("owner") == "皮埃尔"
    items = [
        item for item in package.fact_items
        if item.slot_id == "fact:shop:SeedShop:shop_offer_item"
    ]
    prices = [
        item for item in package.fact_items
        if item.slot_id == "fact:shop:SeedShop:shop_offer_price"
    ]
    assert [item.text_value for item in items] == ["object:472"]
    assert [item.integer_value for item in prices] == [20]
    card = card_of(package, "shop:SeedShop")
    assert card is not None
    assert card.action_summary_1 == "地点：皮埃尔杂货店"
    assert card.action_summary_2 == "营业：随店主日程变化"


# --- 工具与大型可制作物：类型/档位/升级链/解锁（中文） ---


def test_tool_projection_emits_localized_kind_level_and_upgrade_chain(tmp_path: Path) -> None:
    package = build_package(
        tmp_path,
        [
            NormalizedEntity(
                id="tool:CopperPickaxe",
                entity_type="tool",
                game_id="CopperPickaxe",
                internal_name=None,
                name_zh="铜十字镐",
                name_en="Copper Pickaxe",
                description_zh=None,
                description_en=None,
                category=None,
                extra_json={
                    "UpgradeLevel": 1,
                    "ConventionalUpgradeFrom": "(T)Pickaxe",
                    "UpgradeMaterial": "334",
                    "UpgradeMaterialQuantity": 5,
                    "UpgradeCost": 2000,
                },
                source_file="Data/Tools.json",
            ),
            NormalizedEntity(
                id="tool:Pickaxe",
                entity_type="tool",
                game_id="Pickaxe",
                internal_name=None,
                name_zh="十字镐",
                name_en="Pickaxe",
                description_zh=None,
                description_en=None,
                category=None,
                extra_json={"UpgradeLevel": 0},
                source_file="Data/Tools.json",
            ),
        ],
    )
    slots = {
        slot.slot_key: slot
        for slot in package.fact_slots
        if slot.entity_id == "tool:CopperPickaxe"
    }
    assert slots["tool_kind"].text_value == "十字镐"
    assert slots["tool_level"].text_value == "铜"
    assert slots["upgrade_from_id"].text_value == "tool:Pickaxe"
    assert slots["upgrade_location"].text_value == "铁匠铺"
    assert slots["upgrade_time"].text_value == "2 天"
    card = card_of(package, "tool:CopperPickaxe")
    assert card is not None
    assert card.action_summary_1 == "类型：十字镐"
    assert card.action_summary_2 == "档位：铜"


def test_big_craftable_recipe_output_type_and_unlock(tmp_path: Path) -> None:
    package = build_package(
        tmp_path,
        [
            entity("big_craftable:10", "big_craftable", game_id="10"),
            entity("object:388", "object", game_id="388"),
            entity("object:382", "object", game_id="382"),
            entity("object:335", "object", game_id="335"),
            entity("object:724", "object", game_id="724"),
            entity(
                "crafting_recipe:Bee-House",
                "crafting_recipe",
                game_id="Bee House",
                extra_json={
                    "Ingredients": [
                        {"itemId": "388", "quantity": 40},
                        {"itemId": "382", "quantity": 8},
                        {"itemId": "335", "quantity": 1},
                        {"itemId": "724", "quantity": 1},
                    ],
                    "outputItemId": "10",
                    "outputEntityType": "big_craftable",
                    "UnlockCondition": "s Farming 3",
                },
            ),
        ],
    )
    output = slots_of(package, "crafting_recipe:Bee-House", "crafting_output_item_id")[0]
    assert output.text_value == "big_craftable:10", output.text_value
    unlock_items = [
        item
        for item in package.fact_items
        if item.slot_id == "fact:big_craftable:10:unlock"
    ]
    assert [item.text_value for item in unlock_items] == ["耕种等级 3"]
    material_items = [
        item
        for item in package.fact_items
        if item.slot_id == "fact:big_craftable:10:crafting_material_id"
    ]
    assert {item.text_value for item in material_items} == {
        "object:388",
        "object:382",
        "object:335",
        "object:724",
    }


# --- 鱼类：行为/天气/时间/地点必须本地化，卡片摘要按鱼类契约 ---


def fish_fixture(*, with_locations: bool = True) -> tuple[list[NormalizedEntity], object]:
    from builder.sources.official_support import OfficialSupportData

    entities = [
        entity(
            "fish:128",
            "fish",
            game_id="128",
            extra_json={
                "Difficulty": 80,
                "Behavior": "floater",
                "MinSize": 1,
                "MaxSize": 36,
                "FishingTime": "1200 1600",
                "Seasons": ["Summer"],
                "Weather": "sunny",
            },
        ),
    ]
    support: object = None
    if with_locations:
        support = OfficialSupportData(
            locations={
                "Beach": {
                    "Fish": [
                        {
                            "ItemId": "128",
                            "Season": "summer",
                            "Chance": 1.0,
                            "MinDistanceFromShore": 0,
                            "MaxDistanceFromShore": -1,
                        },
                    ],
                },
            }
        )
    return entities, support


def test_fish_profile_slots_are_localized_chinese(tmp_path: Path) -> None:
    entities, support = fish_fixture()
    package = build_package(tmp_path, entities, support=support)
    slots = {
        slot.slot_key: slot for slot in package.fact_slots if slot.entity_id == "fish:128"
    }
    assert slots["behavior"].text_value == "漂浮型", slots["behavior"].text_value
    assert slots["weather"].text_value == "晴天", slots["weather"].text_value
    assert slots["fishing_time"].text_value == "12:00–16:00", slots["fishing_time"].text_value
    assert slots["seasons"].text_value == "夏季", slots["seasons"].text_value
    location_items = [
        item
        for item in package.fact_items
        if item.slot_id == "fact:fish:128:fishing_locations"
    ]
    assert [item.text_value for item in location_items] == ["海滩"], location_items


def test_fish_overnight_time_renders_next_day(tmp_path: Path) -> None:
    entities, _ = fish_fixture(with_locations=False)
    entities[0] = entity(
        "fish:128",
        "fish",
        game_id="128",
        extra_json={
            "Difficulty": 20,
            "Behavior": "mixed",
            "FishingTime": "1800 2600",
            "Seasons": ["Fall"],
            "Weather": "both",
        },
    )
    package = build_package(tmp_path, entities)
    slots = {
        slot.slot_key: slot for slot in package.fact_slots if slot.entity_id == "fish:128"
    }
    assert slots["fishing_time"].text_value == "18:00–次日 2:00", slots["fishing_time"].text_value
    assert slots["weather"].text_value == "不限", slots["weather"].text_value


def test_fish_card_actions_follow_contract(tmp_path: Path) -> None:
    entities, support = fish_fixture()
    package = build_package(tmp_path, entities, support=support)
    card = card_of(package, "fish:128")
    assert card is not None
    assert card.action_summary_1 == "地点：海滩", card.action_summary_1
    assert card.action_summary_2 == "季节：夏季", card.action_summary_2


# --- 怪物：生命/伤害固定事实 + 掉落与地点摘要（中文名解析） ---


def monster_fixture() -> tuple[list[NormalizedEntity], object]:
    from builder.sources.official_support import OfficialSupportData

    entities = [
        entity(
            "monster:Green-Slime",
            "monster",
            game_id="Green Slime",
            extra_json={"monsterHealth": 24, "monsterDamage": 5},
        ),
        NormalizedEntity(
            id="object:766",
            entity_type="object",
            game_id="766",
            internal_name=None,
            name_zh="史莱姆泥",
            name_en=None,
            description_zh=None,
            description_en=None,
            category=None,
            extra_json={},
            source_file="Data/Objects.json",
        ),
        entity(
            "drop:Green-Slime:0",
            "drop",
            game_id="Green-Slime:0",
            extra_json={"monsterId": "Green-Slime", "itemId": "766", "chance": 0.75},
        ),
    ]
    # 空 support 也会触发运行时怪物地点投影（RUNTIME_MONSTER_LOCATION_RULES）。
    support = OfficialSupportData(locations={})
    return entities, support


def test_monster_facts_include_health_and_damage(tmp_path: Path) -> None:
    entities, support = monster_fixture()
    package = build_package(tmp_path, entities, support=support)
    slots = {
        slot.slot_key: slot
        for slot in package.fact_slots
        if slot.entity_id == "monster:Green-Slime"
    }
    assert slots["health"].integer_value == 24, slots.get("health")
    assert slots["damage"].integer_value == 5, slots.get("damage")


def test_monster_card_actions_resolve_locations_and_drops(tmp_path: Path) -> None:
    from builder.pipeline.schema5_projection import RUNTIME_MONSTER_LOCATION_BINDING

    entities, support = monster_fixture()
    package = build_package(
        tmp_path,
        entities,
        support=support,
        game_version=RUNTIME_MONSTER_LOCATION_BINDING[0],
        # 真实候选绑定为 (DLL 哈希, 解包 JSON 哈希)；这里只模拟版本绑定门禁。
        official_release_binding=(RUNTIME_MONSTER_LOCATION_BINDING[1], "fixture-unpacked-hash"),
    )
    card = card_of(package, "monster:Green-Slime")
    assert card is not None
    assert card.action_summary_1 == "地点：矿井", card.action_summary_1
    assert card.action_summary_2 == "掉落：史莱姆泥", card.action_summary_2


# --- 武器：类型本地化 + 伤害区间卡片摘要 ---


def test_weapon_type_fact_and_card_actions(tmp_path: Path) -> None:
    package = build_package(
        tmp_path,
        [
            entity(
                "weapon:1",
                "weapon",
                game_id="1",
                extra_json={
                    "Type": 0,
                    "MinDamage": 8,
                    "MaxDamage": 15,
                    "Speed": 0,
                    "Precision": 0,
                    "Defense": 0,
                    "CritChance": 0.02,
                    "CritMultiplier": 3.0,
                },
            ),
        ],
    )
    slots = {
        slot.slot_key: slot for slot in package.fact_slots if slot.entity_id == "weapon:1"
    }
    assert slots["weapon_type"].text_value == "剑", slots.get("weapon_type")
    card = card_of(package, "weapon:1")
    assert card is not None
    assert card.action_summary_1 == "类型：剑", card.action_summary_1
    assert card.action_summary_2 == "伤害：8–15", card.action_summary_2


# --- 机器规则与物品契约（R4 第 4 波第 1 片） ---


def item_entity(
    entity_id: str,
    entity_type: str,
    name_zh: str,
    *,
    extra_json: dict[str, object] | None = None,
) -> NormalizedEntity:
    return NormalizedEntity(
        id=entity_id,
        entity_type=entity_type,
        game_id=entity_id.split(":", 1)[-1],
        internal_name=None,
        name_zh=name_zh,
        name_en=None,
        description_zh=None,
        description_en=None,
        category=None,
        extra_json=extra_json or {},
        source_file="Data/Objects.json",
    )


def machine_support() -> object:
    from builder.sources.official_support import OfficialSupportData

    return OfficialSupportData(
        machines={
            "(BC)Furnace": {
                "OutputRules": [
                    {
                        "Id": "Default_CopperOre",
                        "MinutesUntilReady": 30,
                        "Triggers": [
                            {
                                "Id": "ItemPlacedInMachine",
                                "Trigger": "ItemPlacedInMachine",
                                "RequiredItemId": "(O)378",
                                "RequiredCount": 5,
                                "RequiredTags": ["category_minerals", "!crystalarium_banned"],
                                "Condition": None,
                            }
                        ],
                    }
                ]
            },
            "(BC)25": {
                "OutputRules": [
                    {
                        "Id": "Default",
                        "MinutesUntilReady": 20,
                        "Triggers": [
                            {
                                "Id": "ItemPlacedInMachine",
                                "Trigger": "ItemPlacedInMachine",
                                "RequiredItemId": None,
                                "RequiredCount": 1,
                                "RequiredTags": ["!seedmaker_banned"],
                                "Condition": None,
                            }
                        ],
                    }
                ]
            },
        }
    )


def test_machine_condition_summaries_are_localized(tmp_path: Path) -> None:
    package = build_package(
        tmp_path,
        [
            item_entity("object:378", "object", "铜矿石", extra_json={"Price": 5}),
            item_entity("big_craftable:Furnace", "big_craftable", "熔炉"),
            item_entity("big_craftable:25", "big_craftable", "种子生产器"),
            # 让 object:378 成为作物收获物：种子生产器行只对作物收获物保留（DLL 规则）。
            item_entity(
                "crop:378",
                "crop",
                "测试作物",
                extra_json={
                    "Seasons": ["Spring"],
                    "DaysInPhase": [1],
                    "RegrowDays": -1,
                    "NeedsWatering": True,
                    "SeedItemId": "378",
                    "HarvestItemId": "378",
                },
            ),
        ],
        support=machine_support(),
    )
    machine_slots = slots_of(package, "object:378", "machine_uses")
    assert machine_slots, "铜矿石缺少机器用途投影"
    summaries = [
        condition.player_summary
        for condition in package.condition_sets
        if condition.id.startswith("condition:machine:")
    ]
    assert summaries, "机器条件缺少本地化摘要"
    joined = "；".join(summaries)
    assert "所需数量：5" in joined, joined
    assert "输入须为：矿物" in joined, joined
    assert "排除：水晶复制器禁用物品" in joined, joined
    assert "排除：种子制造器禁用物品" in joined, joined
    assert "requiredCount" not in joined, joined
    assert "输入标签" not in joined, joined
    machine_condition_ids = {
        condition.id
        for condition in package.condition_sets
        if condition.id.startswith("condition:machine:")
    }
    assert len(machine_condition_ids) == 2, (
        f"两台机器的条件 id 不应合并：{sorted(machine_condition_ids)}"
    )


def test_seed_maker_rows_are_dropped_for_non_crop_harvest_items(tmp_path: Path) -> None:
    package = build_package(
        tmp_path,
        [
            item_entity("object:72", "object", "钻石", extra_json={"Price": 750}),
            item_entity("big_craftable:25", "big_craftable", "种子生产器"),
        ],
        support=machine_support(),
    )
    rows = [
        item.text_value
        for item in package.fact_items
        if item.slot_id == "fact:object:72:machine_uses"
    ]
    assert "big_craftable:25" not in rows, (
        f"非作物收获物不应出现种子生产器行：{rows}"
    )


def test_shop_condition_summaries_are_localized(tmp_path: Path) -> None:
    from builder.sources.official_support import OfficialSupportData

    package = build_package(
        tmp_path,
        [
            item_entity("object:24", "object", "防风草", extra_json={"Price": 35}),
            item_entity("villager:Abigail", "villager", "阿比盖尔"),
        ],
        support=OfficialSupportData(
            shops={
                "SeedShop": {
                    "Currency": 0,
                    "Items": [
                        {
                            "Id": "parsnip-conditional",
                            "ItemId": "(O)24",
                            "Price": 20,
                            "Condition": (
                                "PLAYER_HEARTS Current Abigail 14, "
                                "PLAYER_HAS_MAIL Current JojaMember, "
                                "WEATHER Here Rain"
                            ),
                        }
                    ],
                }
            }
        ),
    )
    summaries = [
        condition.player_summary
        for condition in package.condition_sets
        if condition.player_summary
    ]
    joined = "；".join(summaries)
    assert "阿比盖尔 14 心" in joined, joined
    assert "Joja 会员" in joined, joined
    assert "雨天" in joined, joined
    assert "Current" not in joined and "Here" not in joined and "Rain" not in joined, joined


def test_fish_condition_weather_and_rule_are_localized(tmp_path: Path) -> None:
    from builder.sources.official_support import OfficialSupportData

    entities, _ = fish_fixture(with_locations=False)
    entities.append(item_entity("fish:158", "fish", "石鱼"))
    package = build_package(
        tmp_path,
        entities,
        support=OfficialSupportData(
            locations={
                "Town": {
                    "Fish": [
                        {
                            "ItemId": "(O)128",
                            "Season": "summer",
                            "Chance": 0.5,
                            "Condition": "WEATHER Here Rain Storm GreenRain, "
                            "PLAYER_SPECIAL_ORDER_RULE_ACTIVE Current LEGENDARY_FAMILY, "
                            "TIME 0600 1800",
                        }
                    ]
                }
            }
        ),
    )
    summaries = [
        condition.player_summary
        for condition in package.condition_sets
        if condition.player_summary
    ]
    joined = "；".join(summaries)
    assert "雨天、雷雨天、绿雨天" in joined, joined
    assert "传说之鱼家族任务" in joined, joined
    assert "6:00–18:00" in joined, joined
    assert "Here" not in joined and "LEGENDARY_FAMILY" not in joined, joined


def test_object_card_actions_show_price_uses_and_machines(tmp_path: Path) -> None:
    entities = [
        item_entity("object:378", "object", "铜矿石", extra_json={"Price": 5}),
        item_entity("big_craftable:Furnace", "big_craftable", "熔炉"),
        NormalizedEntity(
            id="crafting_recipe:Furnace",
            entity_type="crafting_recipe",
            game_id="Furnace",
            internal_name=None,
            name_zh="熔炉配方",
            name_en=None,
            description_zh=None,
            description_en=None,
            category=None,
            extra_json={"Ingredients": [{"itemId": "378", "quantity": 20}]},
            source_file="Data/CraftingRecipes.json",
        ),
    ]
    package = build_package(tmp_path, entities, support=machine_support())
    card = card_of(package, "object:378")
    assert card is not None
    assert card.action_summary_1 == "售价：5", card.action_summary_1
    assert card.action_summary_2 == "用途：熔炉配方", card.action_summary_2


def test_ring_card_actions_show_price_and_purchase(tmp_path: Path) -> None:
    from builder.sources.official_support import OfficialSupportData

    package = build_package(
        tmp_path,
        [item_entity("ring:516", "ring", "小型光辉戒指", extra_json={"Price": 100})],
        support=OfficialSupportData(
            shops={
                "AdventureShop": {
                    "Currency": 0,
                    "Items": [{"Id": "glow-ring", "ItemId": "(O)516", "Price": 100}],
                }
            }
        ),
    )
    card = card_of(package, "ring:516")
    assert card is not None
    assert card.action_summary_1 == "售价：100", card.action_summary_1
    assert card.action_summary_2 == "购买价：100", card.action_summary_2


def test_furniture_card_actions_show_purchase(tmp_path: Path) -> None:
    from builder.sources.official_support import OfficialSupportData

    package = build_package(
        tmp_path,
        [item_entity("furniture:0", "furniture", "橡木椅子")],
        support=OfficialSupportData(
            shops={
                "Carpenter": {
                    "Currency": 0,
                    "Items": [{"Id": "oak-chair", "ItemId": "(F)0", "Price": 350}],
                }
            }
        ),
    )
    card = card_of(package, "furniture:0")
    assert card is not None
    assert card.action_summary_1 == "购买价：350", card.action_summary_1


def test_footwear_card_actions_show_defense_and_purchase(tmp_path: Path) -> None:
    from builder.sources.official_support import OfficialSupportData

    package = build_package(
        tmp_path,
        [
            item_entity(
                "footwear:504",
                "footwear",
                "运动鞋",
                extra_json={"footwearDefense": 1, "footwearImmunity": 0},
            ),
        ],
        support=OfficialSupportData(
            shops={
                "AdventureShop": {
                    "Currency": 0,
                    "Items": [{"Id": "sneakers", "ItemId": "(B)504", "Price": 500}],
                }
            }
        ),
    )
    card = card_of(package, "footwear:504")
    assert card is not None
    assert card.action_summary_1 == "防御：1", card.action_summary_1
    assert card.action_summary_2 == "购买价：500", card.action_summary_2


def test_cooking_recipe_materials_include_category_ingredients(tmp_path: Path) -> None:
    package = build_package(
        tmp_path,
        [
            item_entity(
                "cooking_recipe:Maki-Roll",
                "cooking_recipe",
                "生鱼寿司",
                extra_json={"Ingredients": "-4 1 152 1 423 1"},
            ),
            item_entity("object:152", "object", "海草"),
            item_entity("object:423", "object", "大米"),
        ],
    )
    materials = [
        (item.text_value, item.scope_id)
        for item in package.fact_items
        if item.slot_id == "fact:cooking_recipe:Maki-Roll:crafting_material_id"
    ]
    texts = {text for text, _ in materials}
    assert texts == {"任意鱼类", "object:152", "object:423"}, texts
    card = card_of(package, "cooking_recipe:Maki-Roll")
    assert card is not None
    assert card.action_summary_1 == "材料：任意鱼类、海草、大米", card.action_summary_1


# --- 真实 schema 5 候选全量门禁（设置 PLAYER_UI_REAL_CANDIDATE_DB 后运行） ---


def real_candidate_db() -> Path | None:
    raw = os.environ.get("PLAYER_UI_REAL_CANDIDATE_DB")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def iter_player_values(conn: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    """(entity_id, slot_key, scope_id, value) 覆盖所有玩家可读文本事实。"""
    rows: list[tuple[str, str, str, str]] = []
    for entity_id, slot_key, text_value in conn.execute(
        "SELECT entity_id, slot_key, text_value FROM fact_slots WHERE text_value IS NOT NULL"
    ):
        rows.append((entity_id, slot_key, "", text_value))
    for entity_id, slot_key, scope_id, text_value in conn.execute(
        """
        SELECT s.entity_id, s.slot_key, i.scope_id, i.text_value
        FROM fact_items i JOIN fact_slots s ON s.id = i.slot_id
        WHERE i.text_value IS NOT NULL
        """
    ):
        rows.append((entity_id, slot_key, scope_id or "", text_value))
    return rows


# 全槽通用：未解析引用与官方/类别引用一律禁止
UNIVERSAL_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    ("未解析引用", re.compile(r"未解析")),
    ("官方分类引用", re.compile(r"官方分类引用")),
    ("类别引用", re.compile(r"类别引用")),
]

# 礼物槽：不允许原始实体引用（应为已解析中文名）
GIFT_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    ("礼物原始实体引用", re.compile(r"^[a-z_]+:\d+$")),
]

# 日程槽：不允许内部地点代号、Strings 令牌与原始规则
SCHEDULE_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    (
        "日程内部地点代号",
        re.compile(r"\b(SamHouse|JojaMart|CommunityCenter|SeedShop|Desert|Hospital|Beach|"
                   r"JoshHouse|SebastianRoom|Mountain|Saloon|Spa|Forest|Town)\b"),
    ),
    ("日程字符串令牌", re.compile(r'Strings\\\\')),
]

# 村民槽：不允许未本地化官方枚举
VILLAGER_SLOT_RULES: dict[str, tuple[str, re.Pattern[str]]] = {
    "birthday": ("生日未本地化季节", re.compile(r"^(Spring|Summer|Fall|Winter)\b")),
    "gender": ("性别未本地化枚举", re.compile(r"^(Male|Female)$")),
    "residence_region": ("常住地未本地化枚举", re.compile(r"^[A-Za-z]")),
    "seasons": ("季节未本地化枚举", re.compile(r"\b(Spring|Summer|Fall|Winter)\b")),
    "primary_output": ("产物未本地化", re.compile(r"^[^\u4e00-\u9fff]*$")),
    # 鱼类（R4 第 3 波）：行为/天气/时间/地点不得透传官方原文
    "behavior": ("鱼类行为未本地化枚举", re.compile(r"^(floater|dart|smooth|mixed|sinker)$")),
    "weather": ("鱼类天气未本地化枚举", re.compile(r"^(sunny|rainy|both)$")),
    "fishing_time": ("捕捞时间原始格式", re.compile(r"^\d{3,4}\s\d{3,4}$")),
    "fishing_locations": ("捕捞地点未本地化代号", re.compile(r"^[A-Za-z]+$")),
    "weapon_type": ("武器类型未本地化", re.compile(r"^[A-Za-z]+$")),
}


def leak_of(
    entity_id: str,
    slot_key: str,
    value: str,
    known_entity_ids: set[str] | None = None,
) -> str | None:
    for label, pattern in UNIVERSAL_FORBIDDEN:
        if pattern.search(value):
            return label
    if slot_key == "gift_preferences":
        if GIFT_RAW_REFERENCE.fullmatch(value):
            if known_entity_ids is not None and value not in known_entity_ids:
                return "礼物引用无对应实体"
    if slot_key == "schedule":
        for label, pattern in SCHEDULE_FORBIDDEN:
            if pattern.search(value):
                return label
    rule = VILLAGER_SLOT_RULES.get(slot_key)
    if rule is not None:
        label, pattern = rule
        if pattern.search(value):
            return label
    return None


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_has_zero_player_ui_leaks() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        known_entity_ids = {
            row[0] for row in conn.execute("SELECT id FROM entities")
        }
        violations: list[str] = []
        for entity_id, slot_key, scope_id, value in iter_player_values(conn):
            label = leak_of(entity_id, slot_key, value, known_entity_ids)
            if label is not None:
                where = f"{entity_id} / {slot_key}" + (f"[{scope_id}]" if scope_id else "")
                violations.append(f"{where} 包含{label}：{value!r}")
        for condition_id, player_summary in conn.execute(
            "SELECT id, player_summary FROM condition_sets WHERE player_summary IS NOT NULL"
        ):
            for label, pattern in UNIVERSAL_FORBIDDEN:
                if pattern.search(player_summary or ""):
                    violations.append(
                        f"{condition_id} / 条件摘要 包含{label}：{player_summary!r}"
                    )
                    break
        assert not violations, (
            f"真实候选存在 {len(violations)} 处玩家界面泄露，前 12 处："
            + "；".join(violations[:12])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_villager_cards_have_action_summaries() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        missing: list[str] = []
        for entity_id, a1, a2 in conn.execute(
            """
            SELECT c.entity_id, c.action_summary_1, c.action_summary_2
            FROM entity_cards c JOIN entities e ON e.id = c.entity_id
            WHERE e.entity_type = 'villager'
            """
        ):
            if not (a1 and a2):
                missing.append(f"{entity_id}：(a1={a1!r}, a2={a2!r})")
        assert not missing, (
            f"{len(missing)} 个村民卡片缺少契约行动摘要，前 12 个："
            + "；".join(missing[:12])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_villager_portraits_are_full_portraits() -> None:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - 图片门禁需要 PIL
        pytest.skip("缺少 PIL，无法校验图片尺寸")
    conn = sqlite3.connect(real_candidate_db())
    try:
        rows = conn.execute(
            """
            SELECT v.entity_id, v.relative_path FROM visuals v
            JOIN entities e ON e.id = v.entity_id
            WHERE e.entity_type = 'villager' AND v.role = 'entity'
              AND v.status = 'official_own'
            """
        ).fetchall()
        images_dir = real_candidate_db().parent
        violations: list[str] = []
        for entity_id, relative_path in rows:
            path = images_dir / (relative_path or "")
            if not path.is_file():
                violations.append(f"{entity_id} 图片缺失：{relative_path}")
                continue
            with Image.open(path) as image:
                width, height = image.size
            if width < 64:
                violations.append(
                    f"{entity_id} 肖像过窄（{width}x{height}），疑为半脸裁切，"
                    f"路径 {relative_path}"
                )
        assert not violations, (
            f"{len(violations)} 个村民肖像未通过完整度门禁，前 12 个："
            + "；".join(violations[:12])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_manifest_has_chinese_display_names() -> None:
    db_path = real_candidate_db()
    manifest = db_path.parent / "manifest.json"
    if not manifest.is_file():
        pytest.skip("候选目录缺少 manifest.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    browsable = {
        entry["id"]: entry.get("displayName")
        for entry in data.get("content", {}).get("entityTypes", [])
    }
    violations = [
        f"{entity_id} -> {name!r}"
        for entity_id, name in sorted(browsable.items())
        if not name or re.search(r"[A-Za-z_]", name)
    ]
    assert not violations, (
        f"{len(violations)} 个可浏览类型缺少经批准的中文名称："
        + "；".join(violations[:12])
    )


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_monsters_have_health_and_damage() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        missing: list[str] = []
        for entity_id, health, damage in conn.execute(
            """
            SELECT e.id, h.integer_value, d.integer_value
            FROM entities e
            LEFT JOIN fact_slots h ON h.id = 'fact:' || e.id || ':health'
            LEFT JOIN fact_slots d ON d.id = 'fact:' || e.id || ':damage'
            WHERE e.entity_type = 'monster'
            """
        ):
            if health is None or damage is None:
                missing.append(f"{entity_id}（生命={health!r}，伤害={damage!r}）")
        assert not missing, (
            f"{len(missing)} 个怪物缺少生命/伤害固定事实："
            + "；".join(missing[:12])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_wave3_entity_names_are_chinese() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        violations: list[str] = []
        for entity_id, name in conn.execute(
            """
            SELECT id, name_zh FROM entities
            WHERE entity_type IN ('fish', 'monster', 'weapon') AND name_zh IS NOT NULL
            """
        ):
            if not name or not re.search(r"[\u4e00-\u9fff]", name):
                violations.append(f"{entity_id} -> {name!r}")
        assert not violations, (
            f"{len(violations)} 个鱼类/怪物/武器实体名不是中文："
            + "；".join(violations[:12])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_all_browsable_entity_names_are_chinese() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        # 官方故意的神秘名（游戏内即显示为「???」「……」），不视为泄露。
        intentional_mystery_names = {"???", "……"}
        violations: list[str] = []
        for entity_id, name in conn.execute(
            "SELECT id, name_zh FROM entities WHERE name_zh IS NOT NULL AND name_zh != ''"
        ):
            if name in intentional_mystery_names:
                continue
            if not re.search(r"[\u4e00-\u9fff]", name):
                violations.append(f"{entity_id} -> {name!r}")
        assert not violations, (
            f"{len(violations)} 个实体名不是中文（含内部类型）："
            + "；".join(violations[:16])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_machine_condition_summaries_are_chinese() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        violations: list[str] = []
        for condition_id, summary in conn.execute(
            """
            SELECT id, player_summary FROM condition_sets
            WHERE id LIKE 'condition:machine:%' AND player_summary IS NOT NULL
            """
        ):
            if re.search(r"[A-Za-z]", summary):
                violations.append(f"{condition_id} -> {summary!r}")
        assert not violations, (
            f"{len(violations)} 条机器条件摘要泄露英文："
            + "；".join(violations[:12])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_all_condition_summaries_are_chinese() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        violations: list[str] = []
        for condition_id, summary in conn.execute(
            """
            SELECT id, player_summary FROM condition_sets
            WHERE player_summary IS NOT NULL
            """
        ):
            # Joja 是官方品牌拼写，允许；其余拉丁词一律视为泄露。
            residual = summary.replace("Joja", "")
            if re.search(r"[A-Za-z]{2,}", residual):
                violations.append(f"{condition_id} -> {summary!r}")
        assert not violations, (
            f"{len(violations)} 条条件摘要泄露英文："
            + "；".join(violations[:14])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_object_mineral_ring_cards_have_price_summary() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        missing: list[str] = []
        for entity_id, a1 in conn.execute(
            """
            SELECT c.entity_id, c.action_summary_1
            FROM entity_cards c JOIN entities e ON e.id = c.entity_id
            WHERE e.entity_type IN ('object', 'mineral', 'ring')
            """
        ):
            if not a1:
                missing.append(entity_id)
        assert not missing, (
            f"{len(missing)} 个物品/矿物/戒指卡片缺少售价摘要，前 12 个："
            + "；".join(missing[:12])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_weapons_have_weapon_type_facts() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        missing: list[str] = []
        for entity_id, value in conn.execute(
            """
            SELECT e.id, w.text_value
            FROM entities e
            LEFT JOIN fact_slots w ON w.id = 'fact:' || e.id || ':weapon_type'
            WHERE e.entity_type = 'weapon'
            """
        ):
            if not value:
                missing.append(entity_id)
        assert not missing, (
            f"{len(missing)} 把武器缺少武器类型事实："
            + "；".join(missing[:12])
        )
    finally:
        conn.close()


@pytest.mark.skipif(real_candidate_db() is None, reason="未设置 PLAYER_UI_REAL_CANDIDATE_DB")
def test_real_candidate_monster_and_weapon_cards_have_action_summaries() -> None:
    conn = sqlite3.connect(real_candidate_db())
    try:
        missing: list[str] = []
        for entity_id, a1, a2 in conn.execute(
            """
            SELECT c.entity_id, c.action_summary_1, c.action_summary_2
            FROM entity_cards c JOIN entities e ON e.id = c.entity_id
            WHERE e.entity_type = 'weapon'
            """
        ):
            if not (a1 and a2):
                missing.append(f"{entity_id}：(a1={a1!r}, a2={a2!r})")
        # 不可生成的目录型怪物（地点为不适用）不要求契约摘要。
        for entity_id, a1, a2 in conn.execute(
            """
            SELECT c.entity_id, c.action_summary_1, c.action_summary_2
            FROM entity_cards c
            JOIN entities e ON e.id = c.entity_id
            JOIN fact_slots l ON l.id = 'fact:' || e.id || ':locations'
            WHERE e.entity_type = 'monster' AND l.status != 'not_applicable'
            """
        ):
            if not (a1 and a2):
                missing.append(f"{entity_id}：(a1={a1!r}, a2={a2!r})")
        assert not missing, (
            f"{len(missing)} 个怪物/武器卡片缺少契约行动摘要，前 12 个："
            + "；".join(missing[:12])
        )
    finally:
        conn.close()
