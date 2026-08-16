from __future__ import annotations

import hashlib
import json
import math
import re
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
from builder.pipeline.normalize_titles import VILLAGER_DISPLAY_NAMES
from builder.pipeline.normalize_support import drop_chance, percent_label
from builder.pipeline.official_item_index import ItemReferenceResolver, tags_for_entity
from builder.pipeline.official_references import build_reference_index
from builder.pipeline.official_shop_references import build_shop_index, shop_offer
from builder.pipeline.official_values import dictionary_list, entity_ids_for_item, parse_ingredients
from builder.sources.official_support import OfficialSupportData
from builder.utils.hashing import sha256_file

# Every schema-5 projection read goes through the structured channel.  The
# staging wrapper materializes a fixture-only copy before entering this path.
structured_attributes = production_attributes

RELATION_FAMILIES = {"kinship", "friendship", "love_interest"}

# 玩家可读中文规范值（值来自游戏 zh-CN Strings 与社区通用译名；见 RECOVERY R2）。
SEASON_ZH = {"spring": "春季", "summer": "夏季", "fall": "秋季", "winter": "冬季"}

GENDER_ZH = {"Female": "女性", "Male": "男性"}

RESIDENCE_REGION_ZH = {
    "Town": "鹈鹕镇",
    "Desert": "沙漠",
    "Other": "鹈鹕镇周边",
}

# 官方 Object.Category 常量 → 游戏 zh-CN 类别名（来自 GetCategoryDisplayName
# 与 StringsFromCSFiles.zh-CN.json 的逐项对应）。
GIFT_CATEGORY_ZH = {
    -2: "矿物", -12: "矿物",
    -75: "蔬菜",
    -4: "鱼",
    -25: "菜品", -7: "菜品",
    -79: "水果",
    -74: "种子",
    -19: "化肥",
    -21: "鱼饵",
    -22: "钓具",
    -24: "装饰",
    -20: "垃圾",
    -27: "工匠物品", -26: "工匠物品",
    -8: "制造品",
    -18: "动物制品", -14: "动物制品", -6: "动物制品", -5: "动物制品",
    -80: "花",
    -28: "怪物战利品",
    -16: "资源", -15: "资源",
    -81: "采集品",
    -97: "鞋类",
    -100: "服装",
    -96: "戒指",
    -99: "工具",
    -102: "书",
    -103: "技能书",
}

# 礼物列表中的上下文标签 → 中文短语（游戏通过 item.HasContextTag 匹配）。
GIFT_CONTEXT_TAG_ZH = {
    "edible_mushroom": "食用蘑菇",
    "book_item": "书",
    "forage_item_beach": "海滩采集品",
    "ancient_item": "古代物品",
    "doll_item": "玩偶",
    "toy_item": "玩具",
    "category_trinket": "饰品",
    "category_fruits": "水果",
    "category_vegetable": "蔬菜",
    "category_flower": "花",
}

# 日程内部地点代号 → 中文地名（社区通用译名）。
SCHEDULE_LOCATION_ZH = {
    "SamHouse": "山姆家",
    "JoshHouse": "亚历克斯家",
    "HaleyHouse": "海莉家",
    "ScienceHouse": "木匠铺",
    "SebastianRoom": "塞巴斯蒂安的房间",
    "HarveyRoom": "哈维的房间",
    "AnimalShop": "玛妮的牧场",
    "SeedShop": "皮埃尔杂货店",
    "Saloon": "星之果实餐吧",
    "JojaMart": "Joja超市",
    "CommunityCenter": "社区中心",
    "Hospital": "诊所",
    "Blacksmith": "铁匠铺",
    "ArchaeologyHouse": "博物馆",
    "Beach": "海滩",
    "Town": "鹈鹕镇",
    "Mountain": "山区",
    "Forest": "森林",
    "Desert": "沙漠",
    "Railroad": "铁路",
    "BusStop": "公交车站",
    "BathHouse_Entry": "温泉",
    "BathHouse_MensLocker": "温泉",
    "ElliottHouse": "艾利欧特小屋",
    "LeahHouse": "莉亚小屋",
    "LeoTreeHouse": "雷欧的树屋",
    "ManorHouse": "镇长庄园",
    "SandyHouse": "桑迪的家",
    "Tent": "帐篷",
    "Trailer": "房车",
    "FishShop": "鱼店",
    "Sunroom": "阳光房",
    "IslandEast": "姜岛东部",
    "IslandHut": "姜岛小屋",
    "IslandNorth": "姜岛北部",
    "IslandShrine": "姜岛神殿",
    "IslandSouth": "姜岛南部",
    "bed": "回家睡觉",
}

SCHEDULE_DAY_ZH = {
    "Mon": "周一", "Tue": "周二", "Wed": "周三", "Thu": "周四",
    "Fri": "周五", "Sat": "周六", "Sun": "周日",
}

SCHEDULE_SEASON_ZH = {
    "spring": "春季", "summer": "夏季", "fall": "秋季", "winter": "冬季",
}

# 商店动态报价规则的玩家文案（内部 reason 不进入玩家事实）。
PRICE_RULE_REASON_ZH = {
    "runtime-profit-margin": "受利润率设置影响",
    "runtime-sale-price": "基础价由游戏运行时数据决定",
    "object-data-price-unresolved": "基础价来自官方物品数据",
    "conditional-or-random-price-modifier": "受条件或随机价格修正影响",
    "out-of-season-price-rule": "反季节时按游戏规则加价",
}


def localized_seasons(value: object) -> str | None:
    if isinstance(value, list):
        raw = " ".join(str(item).strip() for item in value if str(item).strip())
    else:
        raw = text_value(value)
    if not raw:
        return None
    parts = [part.strip() for part in raw.replace(",", " ").split() if part.strip()]
    localized = [SEASON_ZH.get(part.lower()) for part in parts]
    if all(localized):
        return " ".join(item for item in localized if item)
    return raw


# 商店 → 中文地点（依据官方店主日程与游戏世界知识的人工复核映射；
# 证据链：Data/Shops.json Owners + Characters/schedules 的官方日程）。
SHOP_LOCATION_ZH: dict[str, str] = {
    "SeedShop": "皮埃尔杂货店",
    "AnimalShop": "玛妮的牧场",
    "FishShop": "鱼店",
    "Blacksmith": "铁匠铺",
    "ClintUpgrade": "铁匠铺",
    "Saloon": "星之果实餐吧",
    "AdventureShop": "冒险家公会",
    "AdventureGuildRecovery": "冒险家公会",
    "Carpenter": "木匠铺",
    "Joja": "Joja超市",
    "Hospital": "诊所",
    "Dwarf": "矿井",
    "ShadowShop": "下水道",
    "Sandy": "沙漠",
    "DesertTrade": "沙漠",
    "IslandTrade": "姜岛",
    "VolcanoShop": "姜岛火山",
    "Casino": "沙漠赌场",
    "QiGemShop": "姜岛（齐先生的核桃房）",
    "Raccoon": "森林（大树桩）",
    "HatMouse": "森林（帽子老鼠的旧屋）",
    "IceCreamStand": "鹈鹕镇",
    "Traveler": "森林（旅行货车）",
    "Bookseller": "鹈鹕镇（每月造访）",
    "BooksellerTrade": "鹈鹕镇（每月造访）",
    "BoxOffice": "电影院",
    "Concessions": "电影院",
    "ResortBar": "姜岛度假村",
    "LostItems": "镇长庄园",
    "PetAdoption": "玛妮的牧场",
    "Catalogue": "任意地点（家具目录）",
    "Furniture Catalogue": "任意地点（家具目录）",
    "JojaFurnitureCatalogue": "任意地点（家具目录）",
    "JunimoFurnitureCatalogue": "任意地点（家具目录）",
    "RetroFurnitureCatalogue": "任意地点（家具目录）",
    "TrashFurnitureCatalogue": "任意地点（家具目录）",
    "WizardFurnitureCatalogue": "任意地点（家具目录）",
}

SHOP_CATALOGUE_IDS = {
    "Catalogue",
    "Furniture Catalogue",
    "JojaFurnitureCatalogue",
    "JunimoFurnitureCatalogue",
    "RetroFurnitureCatalogue",
    "TrashFurnitureCatalogue",
    "WizardFurnitureCatalogue",
}

SKILL_ZH = {
    "farming": "耕种",
    "fishing": "钓鱼",
    "foraging": "采集",
    "mining": "采矿",
    "combat": "战斗",
    "luck": "运气",
}

PRESERVE_OUTPUT_ZH = {
    "Honey": "蜂蜜",
    "Jelly": "果酱",
    "Pickle": "泡菜",
    "Wine": "果酒",
    "Juice": "果汁",
    "Roe": "鱼籽",
    "AgedRoe": "陈年鱼籽",
    "DriedFruit": "水果干",
    "DriedMushroom": "蘑菇干",
    "SmokedFish": "熏鱼",
}

TOOL_BASE_KIND_ZH = {
    "axe": "斧头",
    "pickaxe": "十字镐",
    "hoe": "锄头",
    "wateringcan": "喷壶",
    "trashcan": "垃圾桶",
    "pan": "淘盘",
    "scythe": "镰刀",
    "milkpail": "挤奶桶",
    "shears": "剪刀",
}

TOOL_LEVEL_ZH = {0: "基础", 1: "铜", 2: "钢", 3: "金", 4: "铱"}

ROD_LEVEL_ZH = {0: "竹", 2: "玻璃纤维", 3: "铱金", 4: "高级铱金"}

TOOL_LEVEL_PREFIXES = ("copper", "iron", "gold", "iridium", "steel")

# 鱼类与怪物地点：官方内部地图名 → 中文（社区通用译名）。
FISHING_LOCATION_ZH = {
    "Beach": "海滩",
    "Farm_Beach": "海滩（海滩农场）",
    "Farm_Forest": "森林农场",
    "Submarine": "潜水艇（夜市）",
    "fishingGame": "潜水艇钓鱼小游戏",
    "Woods": "秘密森林",
    "Town": "鹈鹕镇",
    "Forest": "森林",
    "Temp": "冰钓节水域",
    "WitchSwamp": "女巫沼泽",
    "Backwoods": "边远森林",
    "BugLand": "突变虫穴",
    "Desert": "沙漠",
    "Mountain": "山区",
    "Sewer": "下水道",
    "UndergroundMine": "矿井",
    "BeachNightMarket": "海滩（夜市）",
    "IslandSouthEastCave": "姜岛东南洞穴",
    "IslandSouthEast": "姜岛东南",
    "IslandSouth": "姜岛南部",
    "IslandWest": "姜岛西部",
    "IslandNorth": "姜岛北部",
    "Caldera": "火山口（火山地牢）",
    "Mine": "矿井",
}

FISH_BEHAVIOR_ZH = {
    "floater": "漂浮型",
    "dart": "冲刺型",
    "smooth": "平滑型",
    "mixed": "混合型",
    "sinker": "下沉型",
}

FISH_WEATHER_ZH = {
    "sunny": "晴天",
    "rainy": "雨天",
    "both": "不限",
}

# MeleeWeapon 常量（DLL）：stabbingSword=0、dagger=1、club=2、defenseSword=3，
# 弹弓（Slingshot）为 4；0 在运行时会被归一为 3，玩家语义都是剑。
WEAPON_TYPE_ZH = {0: "剑", 1: "匕首", 2: "棍棒", 3: "剑", 4: "弹弓"}

# 镰刀在数据里是 Type 0，但 MeleeWeapon.isScythe 覆盖其战斗语义。
WEAPON_SCYTHE_IDS = {"47", "53", "66"}

# 物品上下文/机器输入标签 → 中文（Data/Machines.json RequiredTags 全集 +
# 家具目录 ITEM_CONTEXT_TAG 全集，版本绑定 1.6.15.24356）。
ITEM_TAG_ZH = {
    "category_fish": "鱼类",
    "category_fruits": "水果",
    "category_gem": "宝石",
    "category_greens": "绿叶蔬菜",
    "category_minerals": "矿物",
    "category_vegetable": "蔬菜",
    "egg_item": "蛋类",
    "large_egg_item": "大蛋类",
    "slime_egg_item": "史莱姆蛋",
    "edible_mushroom": "可食用蘑菇",
    "bone_item": "骨头类",
    "keg_juice": "果汁",
    "keg_wine": "酒",
    "preserves_jelly": "果酱",
    "preserves_pickle": "腌菜",
    "preserve_sheet_index_698": "罐头制品",
    "seedmaker_banned": "种子制造器禁用物品",
    "crystalarium_banned": "水晶复制器禁用物品",
    "id_o_881": "火晶石",
    "collection_joja": "Joja 目录",
    "collection_junimo": "祝尼魔目录",
    "collection_retro": "复古目录",
    "collection_trash": "垃圾目录",
    "collection_wizard": "法师目录",
    "collection_catalogue": "目录",
}

# ITEM_EDIBILITY 的玩家文案。
ITEM_EDIBILITY_ZH = {
    "1": "可食用",
    "0": "不可食用",
    "edible": "可食用",
    "inedible": "不可食用",
}

# 邮件标志（PLAYER_HAS_MAIL）→ 中文（1.6.15 官方数据全集）。
MAIL_FLAG_ZH = {
    "CF_Fair": "集市活动",
    "CF_Sewer": "下水道开放",
    "ReturnScepter": "已获得回程魔杖",
    "gotFirstJunimoChest": "已获得第一个祝尼魔箱",
    "gotMissingStocklist": "已获得丢失的库存清单",
    "JojaMember": "Joja 会员",
    "Farm_Eternal": "永恒农场",
    "WillyTropicalFish": "威利的热带鱼任务",
    "galaxySword": "已获得银河剑",
    "ccFishTank": "社区中心鱼缸任务",
    "Egg Festival": "复活节",
    "Ice Festival": "冰雪节",
    "Island_FirstParrot": "姜岛第一只鹦鹉",
    "Island_Turtle": "姜岛海龟",
    "Island_UpgradeBridge": "姜岛桥升级",
    "Island_UpgradeHouse": "姜岛小屋升级",
    "Island_UpgradeParrotPlatform": "姜岛鹦鹉平台",
    "Island_Resort": "姜岛度假村",
    "Island_UpgradeTrader": "姜岛贸易商",
    "Island_W_Obelisk": "姜岛西侧方尖碑",
    "Island_UpgradeHouse_Mailbox": "姜岛小屋邮箱",
    "Island_VolcanoBridge": "姜岛火山桥",
    "Island_VolcanoShortcutOut": "姜岛火山捷径",
}

# 世界状态字段（WORLD_STATE_FIELD）→ 中文。
WORLD_STATE_FIELD_ZH = {
    "GoldenWalnutsFound": "金核桃数量",
    "GoldenCoconutCracked": "金椰子已砸开",
    "TimesFedRaccoons": "喂浣熊次数",
    "VisitsUntilY1Guarantee": "第一年保障访问次数",
}

# 玩家统计字段（PLAYER_STAT）→ 中文。
PLAYER_STAT_ZH = {
    "mastery_1": "耕种精通",
    "mastery_2": "采矿精通",
    "mastery_3": "采集精通",
    "mastery_4": "战斗精通",
    "mastery_5": "钓鱼精通",
    "hardModeMonstersKilled": "困难模式怪物击杀数",
    "ticketPrizesClaimed": "已领取门票奖品数",
}

# 天气值（WEATHER）→ 中文。
WEATHER_VALUE_ZH = {
    "rain": "雨天",
    "storm": "雷雨天",
    "snow": "雪天",
    "greenrain": "绿雨天",
    "sun": "晴天",
    "wind": "大风天",
    "festival": "节日天气",
}

# 被动节日（IS_PASSIVE_FESTIVAL_OPEN）→ 中文。
PASSIVE_FESTIVAL_ZH = {
    "TroutDerby": "鳟鱼大赛",
    "SquidFest": "鱿鱼节",
    "NightMarket": "夜市",
    "DesertFestival": "沙漠节",
}

# 特别订单规则（PLAYER_SPECIAL_ORDER_RULE_ACTIVE）→ 中文。
SPECIAL_ORDER_RULE_ZH = {
    "LEGENDARY_FAMILY": "传说之鱼家族任务",
}

# 博物馆捐赠类别（MUSEUM_DONATIONS）→ 中文。
MUSEUM_DONATION_TYPE_ZH = {
    "Arch": "文物",
    "Minerals": "矿物",
}

# NPC 关系状态（PLAYER_NPC_RELATIONSHIP）→ 中文。
RELATIONSHIP_STATUS_ZH = {
    "Engaged": "订婚",
    "Married": "已婚",
    "Dating": "交往",
    "Friendly": "友好",
    "Roommate": "室友",
}

# 当天同步随机/选择键（SYNCED_RANDOM/SYNCED_CHOICE 的 key）→ 中文。
SYNCED_DAY_KEY_ZH = {
    "cart_rarecrow": "旅行货车稀有稻草人",
    "cart_fez": "旅行货车毡帽",
    "cart_jojaCatalogue": "旅行货车 Joja 目录",
    "cart_retroCatalogue": "旅行货车复古目录",
    "cart_junimoCatalogue": "旅行货车祝尼魔目录",
    "cart_coffee_bean": "旅行货车咖啡豆",
    "fair_tokens": "星币兑换",
    "krobus_bread": "科罗布斯面包",
    "bookExtraForaging": "觅食书",
    "purplebookSale": "紫色书籍促销",
    "secondBookSale": "第二次书籍促销",
    "thirdBookSale": "第三次书籍促销",
    "travelerSkillBook": "旅行者技能书",
    "teaset": "茶具",
    "volcano_roots_platter": "火山根拼盘",
}

# 对话主题（PLAYER_HAS_CONVERSATION_TOPIC）→ 中文。
CONVERSATION_TOPIC_ZH = {
    "willyCrabs": "威利的螃蟹话题",
}

# 价格修正方式与作用域（商店报价规则）。
PRICE_MODIFIER_SCOPE_ZH = {
    "priceModifiers": "商品价格修正",
    "shopPriceModifiers": "商店价格修正",
}
PRICE_MODIFIER_MODE_ZH = {
    "Set": "固定为",
    "Multiply": "乘以",
    "Add": "增加",
}


def localized_fishing_time(value: object) -> str | None:
    """官方 ``600 1900`` 或分时段 ``600 1100 1800 2600`` → 玩家时间文案。"""
    raw = text_value(value)
    if not raw:
        return None
    parts = raw.split()
    if len(parts) >= 2 and len(parts) % 2 == 0 and all(part.isdigit() for part in parts):
        times = [int(part) for part in parts]
        if all(0 <= clock <= 2600 for clock in times):
            sessions: list[str] = []
            for index in range(0, len(times), 2):
                start, end = times[index], times[index + 1]
                start_text = f"{start // 100}:{start % 100:02d}"
                if end > 2400:
                    end_text = f"次日 {end // 100 - 24}:{end % 100:02d}"
                else:
                    end_text = f"{end // 100}:{end % 100:02d}"
                sessions.append(f"{start_text}–{end_text}")
            return "、".join(sessions)
    return raw


def unlock_label(condition: str, by_id: dict[str, NormalizedEntity]) -> str | None:
    """制作配方的官方解锁条件 → 中文玩家文案（CraftingRecipe 语法）。"""
    tokens = condition.split()
    if not tokens:
        return None
    head = tokens[0].casefold()
    if head == "default":
        return "默认解锁"
    if head == "s" and len(tokens) >= 3:
        skill = SKILL_ZH.get(tokens[1].casefold(), tokens[1])
        try:
            level = int(tokens[2])
        except ValueError:
            return None
        return f"{skill}等级 {level}"
    if head in SKILL_ZH and len(tokens) >= 2:
        try:
            level = int(tokens[1])
        except ValueError:
            return None
        return f"{SKILL_ZH[head]}等级 {level}"
    if head == "f" and len(tokens) >= 3:
        name = tokens[1]
        npc = by_id.get(f"villager:{name}")
        name_zh = npc.name_zh if npc is not None else name
        try:
            hearts = int(tokens[2])
        except ValueError:
            return None
        return f"与{name_zh}好感度达到 {hearts}"
    if head == "l" and len(tokens) >= 2:
        try:
            level = int(tokens[1])
        except ValueError:
            return None
        if level <= 0:
            return "默认解锁"
        return f"玩家等级达到 {level}"
    return None


def tool_kind_label(entity: NormalizedEntity) -> str | None:
    name = (entity.game_id or "").casefold()
    if name in {"bamboopole", "fiberglassrod", "iridiumrod", "advancediridiumrod"}:
        return "鱼竿"
    if name.endswith("scythe"):
        return "镰刀"
    base = name
    for prefix in TOOL_LEVEL_PREFIXES:
        if base.startswith(prefix):
            base = base[len(prefix):]
            break
    return TOOL_BASE_KIND_ZH.get(base)


def tool_level_label(entity: NormalizedEntity) -> str | None:
    attributes = structured_attributes(entity)
    level = attributes.get("UpgradeLevel")
    if type(level) is not int:
        return None
    name = (entity.game_id or "").casefold()
    if name in ROD_LEVEL_ZH:
        return ROD_LEVEL_ZH.get(level)
    base = name
    for prefix in TOOL_LEVEL_PREFIXES:
        if base.startswith(prefix):
            base = base[len(prefix):]
            break
    if base.endswith("scythe") or base in {"milkpail", "shears"}:
        return None
    return TOOL_LEVEL_ZH.get(level)


def shop_location_zh(shop_id: str) -> str | None:
    if shop_id.startswith("DesertFestival_"):
        return "沙漠（沙漠节期间）"
    if shop_id.startswith("Festival_NightMarket_"):
        return "海滩（夜市期间）"
    if shop_id.startswith("Festival_"):
        return "鹈鹕镇（节日期间）"
    return SHOP_LOCATION_ZH.get(shop_id)


# 商店性质分类：普通商店优先于节日/临时商店，方便列表主次排序。
SHOP_KIND_PRIORITY = {
    "普通商店": 0,
    "旅行商人": 1,
    "兑换": 1,
    "书摊": 1,
    "赌场": 1,
    "火山商店": 1,
    "其他商店": 2,
    "节日商店": 3,
}

# 节日商店按官方 Shops.json 键名识别（DesertFestival_ / Festival_）。
def classify_shop_kind(shop_id: str) -> str | None:
    if shop_id.startswith(("DesertFestival_", "Festival_")):
        return "节日商店"
    if shop_id in {
        "Traveler",
        "IceCreamStand",
        "BoxOffice",
        "Concessions",
        "ResortBar",
        "PetAdoption",
        "LostItems",
        "AdventureGuildRecovery",
        "ClintUpgrade",
        "Catalogue",
        "Furniture Catalogue",
        "JojaFurnitureCatalogue",
        "JunimoFurnitureCatalogue",
        "RetroFurnitureCatalogue",
        "TrashFurnitureCatalogue",
        "WizardFurnitureCatalogue",
    }:
        return "其他商店"
    if shop_id == "Traveler":
        return "旅行商人"
    if shop_id in {"DesertTrade", "IslandTrade", "QiGemShop", "Raccoon"}:
        return "兑换"
    if shop_id in {"Bookseller", "BooksellerTrade"}:
        return "书摊"
    if shop_id == "Casino":
        return "赌场"
    if shop_id == "VolcanoShop":
        return "火山商店"
    return "普通商店"

# The builder does not evaluate GameStateQuery; it preserves every supported
# predicate as a typed conditional term so the package can accurately state
# what must be true without pretending it knows the player's current save.
GAME_STATE_QUERY_LABELS = {
    "ANY": "满足任一子条件",
    "DAY_OF_MONTH": "日期",
    "DAY_OF_WEEK": "星期",
    "DAYS_PLAYED": "已游玩天数",
    "IS_COMMUNITY_CENTER_COMPLETE": "社区中心完成状态",
    "IS_FESTIVAL_DAY": "节日状态",
    "IS_JOJA_MART_COMPLETE": "Joja 超市完成状态",
    "IS_MULTIPLAYER": "多人模式",
    "IS_PASSIVE_FESTIVAL_OPEN": "被动节日开放状态",
    "ITEM_CONTEXT_TAG": "输入物品标签",
    "ITEM_EDIBILITY": "输入物品可食用性",
    "LOCATION_SEASON": "地点季节",
    "MINE_LOWEST_LEVEL_REACHED": "矿井最深进度",
    "MUSEUM_DONATIONS": "博物馆捐赠数",
    "PLAYER_BASE_FARMING_LEVEL": "玩家基础耕种等级",
    "PLAYER_BASE_FISHING_LEVEL": "玩家基础钓鱼等级",
    "PLAYER_FARMHOUSE_UPGRADE": "农舍升级等级",
    "PLAYER_HAS_ACHIEVEMENT": "玩家成就",
    "PLAYER_HAS_ALL_ACHIEVEMENTS": "玩家全部成就",
    "PLAYER_HAS_CONVERSATION_TOPIC": "玩家对话主题",
    "PLAYER_HAS_CRAFTING_RECIPE": "玩家制作配方",
    "PLAYER_HAS_ITEM": "玩家持有物品",
    "PLAYER_HAS_MAIL": "玩家邮件状态",
    "PLAYER_HAS_SEEN_EVENT": "玩家已观看事件",
    "PLAYER_HAS_TOWN_KEY": "小镇钥匙",
    "PLAYER_HEARTS": "玩家好感度",
    "PLAYER_NPC_RELATIONSHIP": "玩家与村民关系",
    "PLAYER_SPECIAL_ORDER_RULE_ACTIVE": "特别订单规则状态",
    "PLAYER_STAT": "玩家统计值",
    "RANDOM": "随机概率",
    "SEASON": "季节",
    "SYNCED_CHOICE": "同步随机选择",
    "SYNCED_RANDOM": "同步随机概率",
    "TIME": "时间",
    "WEATHER": "天气",
    "WORLD_STATE_FIELD": "世界状态字段",
    "YEAR": "年份",
}
# Accepted argument shapes observed in the version-bound official data. A new
# shape is not silently treated as complete: it remains opaque for review.
GAME_STATE_QUERY_ARGUMENT_COUNTS = {
    "DAY_OF_MONTH": range(1, 32),
    "DAY_OF_WEEK": {1},
    "DAYS_PLAYED": {1},
    "IS_COMMUNITY_CENTER_COMPLETE": {0},
    "IS_FESTIVAL_DAY": {0},
    "IS_JOJA_MART_COMPLETE": {0},
    "IS_MULTIPLAYER": {0},
    "IS_PASSIVE_FESTIVAL_OPEN": {1},
    "ITEM_CONTEXT_TAG": {2},
    "ITEM_EDIBILITY": {2},
    "LOCATION_SEASON": {2, 3, 4},
    "MINE_LOWEST_LEVEL_REACHED": {1},
    "MUSEUM_DONATIONS": {2, 3},
    "PLAYER_BASE_FARMING_LEVEL": {2},
    "PLAYER_BASE_FISHING_LEVEL": {2},
    "PLAYER_FARMHOUSE_UPGRADE": {2},
    "PLAYER_HAS_ACHIEVEMENT": {2},
    "PLAYER_HAS_ALL_ACHIEVEMENTS": {1},
    "PLAYER_HAS_CONVERSATION_TOPIC": {2},
    "PLAYER_HAS_CRAFTING_RECIPE": {2, 3},
    "PLAYER_HAS_ITEM": {2},
    "PLAYER_HAS_MAIL": {2, 3},
    "PLAYER_HAS_SEEN_EVENT": {2},
    "PLAYER_HAS_TOWN_KEY": {1},
    "PLAYER_HEARTS": {3},
    "PLAYER_NPC_RELATIONSHIP": {3, 4, 5},
    "PLAYER_SPECIAL_ORDER_RULE_ACTIVE": {2},
    "PLAYER_STAT": {3},
    "RANDOM": {1, 2, 5},
    "SEASON": {1, 2},
    "SYNCED_CHOICE": {5},
    "SYNCED_RANDOM": {3, 4},
    "TIME": {1, 2},
    "WEATHER": {2, 4},
    "WORLD_STATE_FIELD": {2, 3},
    "YEAR": {1},
}
GAME_STATE_QUERY_MIN_ARGUMENTS = {
    "ANY": 1,
    "DAY_OF_MONTH": 1,
    "DAY_OF_WEEK": 1,
    "DAYS_PLAYED": 1,
    "IS_COMMUNITY_CENTER_COMPLETE": 0,
    "IS_FESTIVAL_DAY": 0,
    "IS_JOJA_MART_COMPLETE": 0,
    "IS_MULTIPLAYER": 0,
    "IS_PASSIVE_FESTIVAL_OPEN": 1,
    "ITEM_CONTEXT_TAG": 2,
    "ITEM_EDIBILITY": 2,
    "LOCATION_SEASON": 2,
    "MINE_LOWEST_LEVEL_REACHED": 1,
    "MUSEUM_DONATIONS": 1,
    "PLAYER_BASE_FARMING_LEVEL": 2,
    "PLAYER_BASE_FISHING_LEVEL": 2,
    "PLAYER_FARMHOUSE_UPGRADE": 2,
    "PLAYER_HAS_ACHIEVEMENT": 2,
    "PLAYER_HAS_ALL_ACHIEVEMENTS": 1,
    "PLAYER_HAS_CONVERSATION_TOPIC": 2,
    "PLAYER_HAS_CRAFTING_RECIPE": 2,
    "PLAYER_HAS_ITEM": 2,
    "PLAYER_HAS_MAIL": 2,
    "PLAYER_HAS_SEEN_EVENT": 2,
    "PLAYER_HAS_TOWN_KEY": 1,
    "PLAYER_HEARTS": 3,
    "PLAYER_NPC_RELATIONSHIP": 3,
    "PLAYER_SPECIAL_ORDER_RULE_ACTIVE": 2,
    "PLAYER_STAT": 3,
    "RANDOM": 1,
    "SEASON": 1,
    "SYNCED_CHOICE": 3,
    "SYNCED_RANDOM": 3,
    "TIME": 2,
    "WEATHER": 2,
    "WORLD_STATE_FIELD": 3,
    "YEAR": 1,
}

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
# This is an official-code audit conclusion, not a missing-acquisition
# exemption. It only applies to the exact DLL and unpacked official-data hashes
# below; a version/hash change leaves the slot not_collected for fresh review.
CURRENT_VERSION_UNOBTAINABLE_WEAPON_IDS = {"34", "49"}
CURRENT_VERSION_UNOBTAINABLE_WEAPON_BINDING = (
    "1.6.15.24356",
    "7f1e5b8e58d2758b78570ba771bbeb03d33522f62188bf6c32edf0cf626deaee",
    "d582dd6b3e9260eee2f26c00d16a14704e4ef44a3d2cf0a4de94f9375c356222",
)

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
# ``Monsters.json`` is a combat-stat catalogue, not a spawn table.  These
# rules mirror the runtime selectors that create the named catalogue monster.
# A rule records a possible player encounter, never a guaranteed spawn rate.
# Runtime location rules are decompiled from this exact game assembly. A
# different game version or DLL hash must be re-audited before it can answer
# location core slots.
RUNTIME_MONSTER_LOCATION_BINDING = (
    "1.6.15.24356",
    "7f1e5b8e58d2758b78570ba771bbeb03d33522f62188bf6c32edf0cf626deaee",
)
RUNTIME_MONSTER_LOCATION_RULES: dict[str, tuple[str, str, str]] = {
    "monster:Bat": (
        "矿井",
        "普通矿井、头骨山洞或采石场矿井的蝙蝠生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Big-Slime": (
        "矿井",
        "史莱姆区域或头骨山洞的巨型史莱姆生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Blue-Squid": (
        "矿井",
        "危险矿井的史莱姆区域或普通矿井层段生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Bug": ("矿井", "普通矿井或头骨山洞的虫类生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Carbon-Ghost": (
        "矿井",
        "危险冰雪矿井或头骨山洞黑暗层生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Duggy": ("矿井", "普通矿井可挖掘地块的生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Dust-Spirit": ("矿井", "冰雪矿井的尘灵生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Dwarvish-Sentry": (
        "火山地牢",
        "火山地牢木桶释放的矮人哨兵",
        "BreakableContainer.releaseContents",
    ),
    "monster:False-Magma-Cap": (
        "火山地牢",
        "火山地牢蘑菇层的假熔岩帽生成规则",
        "VolcanoDungeon.GenerateEntities",
    ),
    "monster:Fly": (
        "矿井",
        "普通矿井、恐龙区域或危险史莱姆区域的苍蝇生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Frost-Bat": ("矿井", "冰雪矿井的蝙蝠变体生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Frost-Jelly": (
        "矿井",
        "冰雪矿井的史莱姆变体生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Ghost": ("矿井", "冰雪矿井 50 层后生成的幽灵", "MineShaft.getMonsterForThisLevel"),
    "monster:Green-Slime": (
        "矿井",
        "矿井、头骨山洞或农场荒野怪物生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Grub": (
        "矿井",
        "普通矿井或危险冰雪矿井的蛆虫生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Hot-Head": ("火山地牢", "火山地牢生成规则", "VolcanoDungeon.GenerateEntities"),
    "monster:Iridium-Bat": (
        "头骨山洞",
        "头骨山洞深层的蝙蝠变体生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Iridium-Crab": (
        "头骨山洞",
        "头骨山洞 146 层后的铱蟹生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Iridium-Golem": (
        "农场",
        "荒野农场怪物的战斗等级变体",
        "Farm.spawnGroundMonsterOffScreen",
    ),
    "monster:Lava-Bat": ("矿井", "岩浆矿井的蝙蝠变体生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Lava-Crab": ("矿井", "岩浆矿井的熔岩蟹生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Lava-Lurk": ("火山地牢", "火山地牢熔岩区生成规则", "VolcanoDungeon.GenerateEntities"),
    "monster:Magma-Duggy": (
        "火山地牢",
        "火山地牢可挖掘地块的生成规则",
        "VolcanoDungeon.GenerateEntities",
    ),
    "monster:Magma-Sparker": (
        "火山地牢",
        "火山地牢蝙蝠的熔岩变体生成规则",
        "VolcanoDungeon.GenerateEntities",
    ),
    "monster:Magma-Sprite": (
        "火山地牢",
        "火山地牢蝙蝠的熔岩变体生成规则",
        "VolcanoDungeon.GenerateEntities",
    ),
    "monster:Metal-Head": ("矿井", "岩浆矿井的铁头生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Mummy": ("头骨山洞", "头骨山洞生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Pepper-Rex": (
        "头骨山洞",
        "头骨山洞 126 层后的恐龙生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Putrid-Ghost": (
        "矿井",
        "危险冰雪矿井 50 层后的幽灵变体",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Rock-Crab": (
        "矿井",
        "普通矿井、危险冰雪矿井或火山地牢的螃蟹生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Royal-Serpent": (
        "头骨山洞",
        "危险头骨山洞的飞蛇变体生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Serpent": ("头骨山洞", "头骨山洞的飞蛇生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Shadow-Brute": (
        "矿井",
        "岩浆矿井或农场荒野怪物生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Shadow-Shaman": (
        "矿井",
        "岩浆矿井的暗影萨满生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Shadow-Sniper": (
        "矿井",
        "危险岩浆矿井的暗影狙击手生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Skeleton": (
        "矿井",
        "冰雪矿井或采石场矿井的骷髅生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Skeleton-Mage": (
        "矿井",
        "危险冰雪矿井的骷髅法师变体",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Sludge": (
        "头骨山洞",
        "头骨山洞或采石场矿井的史莱姆变体",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Spider": ("矿井", "危险史莱姆区域的蜘蛛生成规则", "MineShaft.getMonsterForThisLevel"),
    "monster:Spiker": ("火山地牢", "火山地牢固定尖刺怪生成规则", "VolcanoDungeon.GenerateEntities"),
    "monster:Squid-Kid": (
        "矿井",
        "岩浆矿井或危险头骨山洞的火球小子生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Stone-Golem": (
        "矿井",
        "普通矿井 30 层后的石魔像生成规则",
        "MineShaft.getMonsterForThisLevel",
    ),
    "monster:Tiger-Slime": (
        "火山地牢",
        "火山地牢生成的虎纹史莱姆",
        "VolcanoDungeon.GenerateEntities",
    ),
    "monster:Truffle-Crab": ("农场", "猪挖出松露时的极低概率螃蟹变体", "FarmAnimal.DigUpProduce"),
    "monster:Wilderness-Golem": (
        "农场",
        "荒野农场怪物的石魔像变体",
        "Farm.spawnGroundMonsterOffScreen",
    ),
}
# These legacy stat records are not independently spawnable combat monsters in
# the current game version.  Their location question is therefore explicitly
# outside the combat-monster location contract, rather than an uncollected map.
NON_SPAWNABLE_MONSTER_LOCATION_IDS = {
    "monster:Cat",
    "monster:Crow",
    "monster:Fireball",
    "monster:Frog",
    "monster:Shadow-Guy",
    "monster:Skeleton-Warrior",
}
# 矿井层段（中文维基·矿井楼层表）：怪物出现的矿井楼层范围。
# 只收录普通矿井有明确楼层说明的怪物；农场荒野、火山地牢等没有
# 矿井楼层语义的怪物不在此表（用户文案中保留其实际出现地点）。
# 楼层表 2026-08 核对的官方中文维基页面版本。
WIKI_REVISION_AT = "2026-08-16T00:00:00+08:00"
MONSTER_MINE_FLOORS: dict[str, str] = {
    "monster:Green-Slime": "矿井 1-39 层",
    "monster:Duggy": "矿井 1-39 层",
    "monster:Bug": "矿井 1-39 层",
    "monster:Rock-Crab": "矿井 1-39 层",
    "monster:Grub": "矿井 1-39 层",
    "monster:Fly": "矿井 1-39 层",
    "monster:Bat": "矿井 31-39 层",
    "monster:Stone-Golem": "矿井 31-39 层",
    "monster:Frost-Jelly": "矿井 40-79 层",
    "monster:Frost-Bat": "矿井 40-79 层",
    "monster:Dust-Spirit": "矿井 40-79 层",
    "monster:Ghost": "矿井 51-79 层",
    "monster:Skeleton": "矿井 61-79 层",
    "monster:Skeleton-Mage": "矿井 61-79 层",
    "monster:Carbon-Ghost": "矿井 40-79 层",
    "monster:Blue-Squid": "矿井 40-79 层",
    "monster:Putrid-Ghost": "矿井 40-79 层",
    "monster:Lava-Crab": "矿井 80-119 层",
    "monster:Lava-Bat": "矿井 80-119 层",
    "monster:Shadow-Brute": "矿井 80-119 层",
    "monster:Shadow-Shaman": "矿井 80-119 层",
    "monster:Shadow-Sniper": "矿井 80-119 层",
    "monster:Metal-Head": "矿井 80-119 层",
    "monster:Squid-Kid": "矿井 80-119 层",
    "monster:Magma-Sparker": "矿井 80-119 层",
    "monster:Magma-Sprite": "矿井 80-119 层",
}
# These legacy rows are ambient/non-combat records, not killable enemies. Their
# old stat-catalogue drops cannot answer player loot in the current game.
NON_COMBAT_MONSTER_DROP_IDS = {"monster:Cat", "monster:Crow", "monster:Frog"}


SPECIAL_WEAPON_ACQUISITION_RULES: dict[str, tuple[str, str, str]] = {
    "2": (
        "闹鬼骷髅的诅咒娃娃变体随机掉落",
        "Bat.getExtraDropItems",
        "official-haunted-skull-drop-to-weapon-acquisition-v1",
    ),
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
    "65": (
        "森林传送柱事件奖励",
        "GameLocation.performAction:ForestPylon",
        "official-forest-pylon-event-to-weapon-acquisition-v1",
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
    official_release_binding: tuple[str, str] | None = None,
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
    if support is not None:
        entities = resolve_tailoring_output_names(entities, support)
        by_id = {entity.id: entity for entity in entities}
    gift_index, universal_gift, drop_index = build_item_relation_indexes(entities)
    shop_index = build_recipe_shop_index(entities)
    fish_pond_index = build_fish_pond_index(support, by_id)
    museum_index = build_museum_reward_index(support, by_id)
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
        fact_slots = typed_facts(
            entity,
            by_id=by_id,
            gift_index=gift_index,
            universal_gift=universal_gift,
            drop_index=drop_index,
            shop_index=shop_index,
            fish_pond_index=fish_pond_index,
            museum_index=museum_index,
            support=support,
        )
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
            package,
            entities,
            support,
            entity_ids,
            game_version,
            locators_by_entity,
            official_release_binding,
        )
        add_shop_projections(
            package,
            entities,
            support,
            source_documents,
            source_locators,
            game_version,
        )
        add_big_craftable_purpose_projections(
            package,
            entities,
            support,
            source_documents,
            source_locators,
            game_version,
        )
    if support_entities:
        add_villager_support_projections(package, support_entities, by_id, game_version)
    project_card_actions(package)
    return package


def distinct_text_items(items: list[Schema5FactItem]) -> list[str]:
    """Order-preserving distinct non-empty item text values."""
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.text_value
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def project_card_actions(package: Schema5Package) -> None:
    """Derive the two list-level action answers from typed fact rows.

    Slot priority follows each category contract so the more important
    summary always lands on the first line (决策 04/10)。
    """
    slots_by_entity: dict[str, list[Schema5FactSlot]] = defaultdict(list)
    for slot in package.fact_slots:
        slots_by_entity[slot.entity_id].append(slot)
    items_by_slot: dict[str, list[Schema5FactItem]] = defaultdict(list)
    for item in package.fact_items:
        items_by_slot[item.slot_id].append(item)
    entity_types = {entity.id: entity.entity_type for entity in package.entities}
    entity_names = {entity.id: entity.name_zh for entity in package.entities}
    priority_by_type = {
        "crop": ("seasons", "first_harvest_days", "seed_purchase_price", "sell_price"),
        "villager": ("birthday", "residence_region"),
        "fish": ("fishing_locations", "seasons"),
        "shop": ("location", "opening_hours"),
        "tool": ("tool_kind", "tool_level", "upgrade_price"),
        "big_craftable": ("primary_output", "unlock", "upgrade_price"),
        "monster": ("locations", "drops"),
        "weapon": ("weapon_type", "damage_min"),
        "object": ("sell_price", "used_in", "machine_uses"),
        "mineral": ("sell_price", "used_in", "machine_uses"),
        "ring": ("sell_price", "purchase_price"),
        "furniture": ("purchase_price", "purchase_exchange_item_id"),
        "footwear": ("defense", "purchase_price"),
        "cooking_recipe": ("crafting_material_id",),
        "crafting_recipe": ("crafting_material_id",),
        "quest": ("quest_type", "quest_objective", "quest_reward"),
        "achievement": ("achievement_description",),
        "bundle": ("bundle_area", "bundle_ingredients"),
        "special_order": (
            "special_order_duration",
            "special_order_objective",
            "special_order_requester",
        ),
    }
    updated = []
    for card in package.entity_cards:
        entity_type = entity_types.get(card.entity_id, "")
        slots = sorted(slots_by_entity.get(card.entity_id, []), key=lambda item: item.slot_key)
        priority = priority_by_type.get(entity_type, ())
        ordered = sorted(slots, key=lambda slot: (
            priority.index(slot.slot_key) if slot.slot_key in priority else len(priority),
            slot.slot_key,
        ))
        actions: list[str] = []
        for slot in ordered:
            if slot.status not in {"fixed", "conditional", "dynamic_rule"}:
                continue
            if slot.slot_key in {"sell_price", "purchase_price", "seed_purchase_price"}:
                value = slot.integer_value
                if value is None:
                    # 支持槽的价格放在事实项上（商店报价投影）。
                    value = next(
                        (
                            item.integer_value
                            for item in items_by_slot.get(slot.id, [])
                            if item.integer_value is not None
                        ),
                        None,
                    )
                if value is not None:
                    label = {
                        "sell_price": "售价",
                        "purchase_price": "购买价",
                        "seed_purchase_price": "种子价",
                    }[slot.slot_key]
                    actions.append(f"{label}：{value}")
                elif slot.status == "dynamic_rule":
                    # 动态报价（目录/基础价规则）以规则文案作为卡片答案。
                    rule_slot = next(
                        (
                            candidate
                            for candidate in slots
                            if candidate.slot_key
                            in {"purchase_price_rule", "seed_purchase_price_rule"}
                        ),
                        None,
                    )
                    rule_text = None
                    if rule_slot is not None:
                        rule_text = next(
                            (
                                item.text_value
                                for item in items_by_slot.get(rule_slot.id, [])
                                if item.text_value
                            ),
                            None,
                        )
                    if rule_text:
                        actions.append(f"购买：{rule_text}")
            elif slot.slot_key == "seasons" and slot.text_value:
                actions.append(f"季节：{slot.text_value}")
            elif slot.slot_key in {"fishing_locations", "locations"}:
                values = distinct_text_items(items_by_slot.get(slot.id, []))
                if values:
                    actions.append(f"地点：{'、'.join(values[:3])}")
            elif slot.slot_key == "drops":
                values = distinct_text_items(items_by_slot.get(slot.id, []))
                names: list[str] = []
                seen_names: set[str] = set()
                for value in values:
                    name = entity_names.get(value)
                    if name and name not in seen_names:
                        seen_names.add(name)
                        names.append(name)
                if names:
                    actions.append(f"掉落：{'、'.join(names[:3])}")
            elif slot.slot_key in {"used_in", "machine_uses", "crafting_material_id"}:
                values = distinct_text_items(items_by_slot.get(slot.id, []))
                names: list[str] = []
                seen_names: set[str] = set()
                for value in values:
                    name = entity_names.get(value)
                    if name is None:
                        # 类别材料（任意鱼类）等中文文案直接展示；跳过未解析引用。
                        if ":" in value or value.startswith("-"):
                            continue
                        name = value
                    if name not in seen_names:
                        seen_names.add(name)
                        names.append(name)
                if names:
                    label = {
                        "crafting_material_id": "材料",
                        "used_in": "用途",
                        "machine_uses": "加工",
                    }[slot.slot_key]
                    actions.append(f"{label}：{'、'.join(names[:3])}")
            elif slot.slot_key == "birthday" and slot.text_value:
                actions.append(f"生日：{slot.text_value}")
            elif slot.slot_key == "residence_region" and slot.text_value:
                actions.append(f"常住：{slot.text_value}")
            elif slot.slot_key == "first_harvest_days" and slot.integer_value is not None:
                actions.append(f"成熟：{slot.integer_value} 天")
            elif slot.slot_key == "damage_min" and slot.integer_value is not None:
                damage_max = next(
                    (
                        candidate.integer_value
                        for candidate in slots
                        if candidate.slot_key == "damage_max"
                        and candidate.integer_value is not None
                    ),
                    None,
                )
                if damage_max is not None:
                    actions.append(f"伤害：{slot.integer_value}–{damage_max}")
                else:
                    actions.append(f"伤害：{slot.integer_value}")
            elif slot.slot_key == "defense" and slot.integer_value is not None:
                actions.append(f"防御：{slot.integer_value}")
            elif slot.slot_key in {"location", "opening_hours", "owner"}:
                values = [
                    item.text_value
                    for item in items_by_slot.get(slot.id, [])
                    if item.text_value
                ]
                if values:
                    label = {
                        "location": "地点",
                        "opening_hours": "营业",
                        "owner": "店主",
                    }[slot.slot_key]
                    actions.append(f"{label}：{values[0]}")
            elif slot.slot_key == "upgrade_price" and slot.integer_value is not None:
                actions.append(f"升级：{slot.integer_value} 金币")
            elif slot.slot_key in {
                "tool_kind", "tool_level", "primary_output", "unlock", "weapon_type",
                "quest_type", "quest_objective", "quest_reward",
                "achievement_description", "bundle_area", "bundle_ingredients",
                "special_order_duration", "special_order_objective", "special_order_requester",
            }:
                label = {
                    "tool_kind": "类型",
                    "tool_level": "档位",
                    "primary_output": "产物",
                    "unlock": "解锁",
                    "weapon_type": "类型",
                    "quest_type": "类型",
                    "quest_objective": "目标",
                    "quest_reward": "奖励",
                    "achievement_description": "解锁",
                    "bundle_area": "区域",
                    "bundle_ingredients": "所需",
                    "special_order_duration": "时限",
                    "special_order_objective": "目标",
                    "special_order_requester": "委托人",
                }[slot.slot_key]
                value = slot.text_value or next(
                    (
                        item.text_value
                        for item in items_by_slot.get(slot.id, [])
                        if item.text_value
                    ),
                    None,
                )
                if value:
                    actions.append(f"{label}：{value}")
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
    official_release_binding: tuple[str, str] | None = None,
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
        official_release_binding=official_release_binding,
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
    ordinals_by_slot: dict[str, int] = defaultdict(int)
    for item in package.fact_items:
        ordinals_by_slot[item.slot_id] = max(
            ordinals_by_slot[item.slot_id], item.ordinal + 1
        )
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
                slot_id = f"fact:{villager_id}:schedule"
                ordinal = ordinals_by_slot[slot_id]
                add_support_fact_item(
                    package,
                    villager_id,
                    "schedule",
                    "text",
                    text_value=text,
                    scope_id=f"schedule:{support_entity.game_id}",
                    condition_set_id=None,
                    ordinal=ordinal,
                    locator_id=locator_id,
                    transformation_rule="official-npc-schedule-to-player-facts-v1",
                )
                ordinals_by_slot[slot_id] += 1
        elif support_entity.entity_type == "villager_gift":
            slot_id = f"fact:{villager_id}:gift_preferences"
            for item_index, (preference, item) in enumerate(
                gift_fact_items(attributes, by_id, package.gift_reference_diagnostics)
            ):
                ordinal = ordinals_by_slot[slot_id]
                add_support_fact_item(
                    package,
                    villager_id,
                    "gift_preferences",
                    "text",
                    text_value=item,
                    scope_id=(
                        f"gift:{stable_part(support_entity.id)}:"
                        f"{stable_part(preference)}:{item_index}"
                    ),
                    condition_set_id=None,
                    ordinal=ordinal,
                    locator_id=locator_id,
                    transformation_rule="official-villager-gifts-to-player-facts-v1",
                )
                ordinals_by_slot[slot_id] += 1
    package.source_documents = sorted(documents.values(), key=lambda item: item.id)
    package.source_locators = sorted(locators.values(), key=lambda item: item.id)


def schedule_fact_text(attributes: dict[str, Any]) -> str | None:
    location = text_value(attributes.get("location") or attributes.get("Location"))
    time = text_value(attributes.get("time") or attributes.get("Time"))
    schedule = text_value(attributes.get("schedule") or attributes.get("Schedule"))
    entries = attributes.get("ScheduleEntries")
    if isinstance(entries, list):
        rendered_entries = render_schedule_entries(entries)
        if rendered_entries:
            schedule = "；".join(rendered_entries)
    parts = [
        part
        for part in (
            f"时间：{localized_schedule_time(time)}" if time else None,
            f"地点：{SCHEDULE_LOCATION_ZH.get(location, localized_schedule_location(location))}"
            if location
            else None,
        )
        if part
    ]
    if schedule:
        parts.append(schedule)
    return "；".join(parts) or None


def render_schedule_entries(entries: list[dict[str, Any]]) -> list[str]:
    """把一天内的官方日程段渲染为中文时间线，连续同地点合并为时间段。

    官方一条日程（如镇长周二）是「时间 地点 坐标 动画」的路径段序列，
    同一地点常常出现多个连续段（如 8:00/10:00 都在镇长庄园）；合并后
    展示为「8:00–14:00 镇长庄园」，让玩家一眼看出几点到几点在哪。
    """
    parts: list[str] = []
    current: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        start = localized_schedule_time(str(current["start"]))
        if current["end"] is not None:
            end = localized_schedule_time(str(current["end"]))
            parts.append(f"{start}–{end} {current['label']}")
        else:
            parts.append(f"{start} {current['label']}")
        current = None

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if "rule" in entry:
            flush()
            rule_text = render_schedule_rule(text_value(entry.get("rule")) or "")
            if rule_text:
                parts.append(rule_text)
            continue
        entry_time = entry.get("time")
        entry_location = text_value(entry.get("location"))
        if not (isinstance(entry_time, int) and entry_location):
            continue
        location_zh = localized_schedule_location(entry_location)
        if location_zh is None:
            continue
        if current is not None and current["label"] == location_zh:
            current["end"] = entry_time
            continue
        flush()
        current = {"start": entry_time, "end": None, "label": location_zh}
    flush()
    return parts


def render_schedule_entry(entry: dict[str, Any]) -> str | None:
    """把单条官方日程渲染为中文玩家文案，丢弃坐标/动画等内部 token。"""
    entry_time = entry.get("time")
    entry_location = text_value(entry.get("location"))
    if isinstance(entry_time, int) and entry_location:
        location_zh = localized_schedule_location(entry_location)
        if location_zh is None:
            return None
        return f"{localized_schedule_time(str(entry_time))} {location_zh}"
    rule = text_value(entry.get("rule"))
    if rule:
        return render_schedule_rule(rule)
    return None


def render_schedule_rule(rule: str) -> str | None:
    tokens = rule.split()
    if not tokens:
        return None
    head = tokens[0]
    if head == "GOTO":
        target = tokens[1] if len(tokens) > 1 else ""
        return f"与{localized_schedule_key(target)}相同"
    if head == "NOT" and len(tokens) >= 4 and tokens[1] == "friendship":
        name = localized_schedule_name(tokens[2])
        try:
            level = int(tokens[3])
        except ValueError:
            return "受好感度条件限制"
        return f"需与{name}好感度低于{level}"
    if head == "MAIL":
        return "受邮件事件条件限制"
    if head.startswith("a") and head[1:].isdigit():
        # 动画时刻（a1000 等）不承载玩家信息。
        return None
    if head in SCHEDULE_LOCATION_ZH:
        location_zh = SCHEDULE_LOCATION_ZH[head]
        return f"留在{location_zh}"
    return None


def localized_schedule_time(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        minutes = int(raw)
    except ValueError:
        hours, separator, minutes_part = raw.partition(":")
        if separator and hours.isdigit() and minutes_part.isdigit():
            try:
                minutes = int(hours) * 100 + int(minutes_part)
            except ValueError:
                return None
        else:
            return None
    if not 0 <= minutes <= 2600:
        return None
    return f"{minutes // 100}:{minutes % 100:02d}"


def localized_schedule_location(location: str) -> str | None:
    return SCHEDULE_LOCATION_ZH.get(location)


def localized_schedule_key(key: str) -> str:
    if key in ("NO_SCHEDULE", "NO_SCHEDULE_OWN"):
        return "当日无固定日程"
    if key in SCHEDULE_DAY_ZH:
        return SCHEDULE_DAY_ZH[key]
    if key in SCHEDULE_SEASON_ZH:
        return SCHEDULE_SEASON_ZH[key]
    if key == "rain":
        return "雨天"
    if key == "season":
        return "当季"
    for day, day_zh in SCHEDULE_DAY_ZH.items():
        if key.startswith(day):
            suffix = key.removeprefix(day)
            if suffix in ("", "_normal"):
                return day_zh + ("（常规）" if suffix else "")
            if suffix.startswith("_") and suffix[1:].isdigit():
                return f"{day_zh}（每月{suffix[1:]}日）"
            return f"{day_zh}（{suffix.lstrip('_')}）"
    for season, season_zh in SCHEDULE_SEASON_ZH.items():
        if key.startswith(season):
            suffix = key.removeprefix(season)
            if not suffix:
                return season_zh
            if suffix.startswith("_") and suffix[1:].isdigit():
                return f"{season_zh}（每月{suffix[1:]}日）"
            if suffix == "_noBridge":
                return f"{season_zh}（桥修复前）"
            return f"{season_zh}（{suffix.lstrip('_')}）"
    if key.startswith("marriage_"):
        inner = key.removeprefix("marriage_")
        return f"婚后（{localized_schedule_key(inner)}）"
    if key.isdigit():
        return f"每月{key}日"
    # 未识别日程键不进入玩家文案；由真实候选门禁保证不出现。
    return "其他日程"


def localized_schedule_name(name: str) -> str:
    return {
        "Sebastian": "塞巴斯蒂安",
        "Haley": "海莉",
        "Leah": "莉亚",
        "Alex": "亚历克斯",
        "Sam": "山姆",
        "Penny": "潘妮",
        "Abigail": "阿比盖尔",
        "Elliott": "艾利欧特",
        "Emily": "艾米丽",
        "Harvey": "哈维",
        "Jodi": "乔迪",
        "Kent": "肯特",
        "Lewis": "刘易斯",
        "Linus": "莱纳斯",
        "Maru": "玛鲁",
        "Pierre": "皮埃尔",
        "Robin": "罗宾",
        "Shane": "谢恩",
        "Willy": "威利",
        "Wizard": "法师",
        "Krobus": "科罗布斯",
    }.get(name, name)


def gift_fact_items(
    attributes: dict[str, Any],
    by_id: dict[str, NormalizedEntity],
    diagnostics: list[dict[str, object]] | None = None,
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
                rendered = render_gift_reference(value, by_id, diagnostics)
                if rendered is not None:
                    result.append((preference, rendered))
        return result
    raw = attributes.get("items") or attributes.get("Items") or attributes.get("itemIds")
    values = raw if isinstance(raw, list) else [raw]
    return [
        ("unknown", rendered)
        for value in values
        if (rendered := render_gift_reference(value, by_id, diagnostics)) is not None
    ]


def render_gift_reference(
    value: object,
    by_id: dict[str, NormalizedEntity],
    diagnostics: list[dict[str, object]] | None = None,
) -> str | None:
    """把礼物 token 渲染为类型化实体引用或中文类别短语。

    实体引用（``object:72``、``trinket:FrogEgg``）是 schema 5 跨仓库契约，
    由 App 解析为可点击中文实体；类别码与上下文标签渲染为中文短语；
    无法解析的 token 不进入玩家事实，只记入构建诊断。
    """
    reference = stable_entity_reference(value, by_id)
    if reference is not None:
        return reference
    raw = text_value(value)
    if raw is None:
        return None
    if raw.startswith("category_"):
        tag = raw.removeprefix("category_")
        label = GIFT_CONTEXT_TAG_ZH.get(raw) or GIFT_CONTEXT_TAG_ZH.get(tag)
        if label is not None:
            return label
        note_unresolved_gift(diagnostics, raw, "未识别上下文标签")
        return None
    if raw.startswith("-") and raw[1:].isdigit():
        label = GIFT_CATEGORY_ZH.get(int(raw))
        if label is not None:
            return label
        note_unresolved_gift(diagnostics, raw, "未识别官方类别码")
        return None
    label = GIFT_CONTEXT_TAG_ZH.get(raw)
    if label is not None:
        return label
    note_unresolved_gift(diagnostics, raw, "无法解析为实体或已知类别")
    return None


def note_unresolved_gift(
    diagnostics: list[dict[str, object]] | None, token: str, reason: str
) -> None:
    if diagnostics is None:
        return
    diagnostics.append({"token": token, "reason": reason})


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
    official_release_binding: tuple[str, str] | None = None,
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
            condition, condition_terms = fish_condition(reference, item_id, by_id)
            condition_id = condition.id if condition is not None else None
            if condition is not None:
                package.condition_sets.append(condition)
                package.condition_terms.extend(condition_terms)
            fact_item = Schema5FactItem(
                id=item_id,
                slot_id=slot_id,
                ordinal=ordinal,
                value_type="text",
                text_value=FISHING_LOCATION_ZH.get(str(reference["locationId"])),
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
                by_id,
            )
            item = add_support_fact_item(
                package,
                monster_id,
                "locations",
                "text",
                text_value=FISHING_LOCATION_ZH.get(str(reference["locationId"])),
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
    add_runtime_monster_location_projections(
        package,
        entities,
        source_documents,
        source_locators,
        game_version,
        official_release_binding,
    )
    add_monster_floor_facts(
        package,
        entities,
        source_documents,
        source_locators,
        game_version,
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
        official_release_binding,
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


def add_monster_floor_facts(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    source_documents: dict[str, Schema5SourceDocument],
    source_locators: dict[str, Schema5SourceLocator],
    game_version: str,
) -> None:
    """矿井层段（楼层）作为补充事实：玩家最关心怪物在哪一层出现。

    数据来自星露谷官方中文维基的矿井楼层表，以 supplemental 来源区分于
    官方运行时出现规则；没有楼层语义的怪物不生成该事实。
    """
    source_id = "source:supplemental:wiki-mine-floors"
    source_documents.setdefault(
        source_id,
        Schema5SourceDocument(
            id=source_id,
            source_kind="supplemental",
            title="星露谷官方中文维基 · 矿井楼层表",
            game_version=game_version,
            source_url="https://zh.stardewvalleywiki.com/矿井",
            revision="zh-wiki-mines-floor-table-v1",
            revision_at=WIKI_REVISION_AT,
            platform="web",
            language="zh-CN",
            reviewed_at=WIKI_REVISION_AT,
            review_status="approved",
        ),
    )
    for entity in entities:
        if entity.entity_type != "monster":
            continue
        floors = MONSTER_MINE_FLOORS.get(entity.id)
        if floors is None:
            continue
        slot_id = f"fact:{entity.id}:floors"
        if any(slot.id == slot_id for slot in package.fact_slots):
            continue
        locator_id = f"locator:supplemental:wiki-mine-floors:{stable_part(entity.id)}"
        source_locators.setdefault(
            locator_id,
            Schema5SourceLocator(
                id=locator_id,
                source_document_id=source_id,
                source_file="矿井",
                record_key=entity.id,
            ),
        )
        package.fact_slots.append(
            Schema5FactSlot(
                id=slot_id,
                entity_id=entity.id,
                slot_key="floors",
                status="fixed",
                value_type="text",
                text_value=floors,
            )
        )
        evidence_id = f"evidence:fact:{stable_part(slot_id)}"
        package.evidence.append(
            Schema5Evidence(
                id=evidence_id,
                source_locator_id=locator_id,
                evidence_kind="supplemental",
                transformation_rule="wiki-mine-floors-to-player-facts-v1",
            )
        )
        package.claim_evidence.append(
            Schema5ClaimEvidence(slot_id, evidence_id, "fact_slot")
        )


def add_runtime_monster_location_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    source_documents: dict[str, Schema5SourceDocument],
    source_locators: dict[str, Schema5SourceLocator],
    game_version: str,
    official_release_binding: tuple[str, str] | None,
) -> None:
    """Project version-bound monster encounters from official runtime selectors."""
    expected_version, expected_dll_hash = RUNTIME_MONSTER_LOCATION_BINDING
    if (
        game_version != expected_version
        or official_release_binding is None
        or official_release_binding[0] != expected_dll_hash
    ):
        return
    monster_ids = {entity.id for entity in entities if entity.entity_type == "monster"}

    source_id = "source:official-rule:monster-locations"
    source_documents.setdefault(
        source_id,
        Schema5SourceDocument(
            id=source_id,
            source_kind="official_derived",
            title="Stardew Valley.dll · runtime monster spawn rules",
            game_version=game_version,
            content_hash=expected_dll_hash,
        ),
    )
    for monster_id, (location, summary, method) in sorted(RUNTIME_MONSTER_LOCATION_RULES.items()):
        if monster_id not in monster_ids:
            continue
        locator_id = f"locator:official-rule:monster-location:{stable_part(method)}"
        source_locators.setdefault(
            locator_id,
            Schema5SourceLocator(
                id=locator_id,
                source_document_id=source_id,
                source_file="Stardew Valley.dll",
                record_key=method,
            ),
        )
        condition_id = f"condition:monster-location-runtime:{stable_part(monster_id)}"
        package.condition_sets.append(
            Schema5ConditionSet(
                id=condition_id,
                # This table preserves the official method and a player-readable
                # encounter summary, not every runtime branch operand.
                completeness="partial",
                player_summary=summary,
            )
        )
        package.condition_terms.append(
            Schema5ConditionTerm(
                id=f"condition-term:{stable_part(condition_id)}:runtime-spawn",
                condition_set_id=condition_id,
                ordinal=0,
                kind="runtime_spawn_rule",
                value_text=summary,
            )
        )
        slot_id = f"fact:{monster_id}:locations"
        ordinal = sum(1 for item in package.fact_items if item.slot_id == slot_id)
        item = add_support_fact_item(
            package,
            monster_id,
            "locations",
            "text",
            text_value=location,
            scope_id=f"monster-location-runtime:{monster_id}",
            condition_set_id=condition_id,
            ordinal=ordinal,
            locator_id=locator_id,
            transformation_rule="official-runtime-monster-location-to-player-facts-v1",
            status="conditional",
            fact_condition_set_id=condition_id,
        )
        add_support_facet(
            package,
            entity_id=monster_id,
            family="monster_location",
            item=item,
            condition_set_id=condition_id,
            locator_id=locator_id,
            transformation_rule="official-runtime-monster-location-to-player-facts-v1",
        )
    for monster_id in sorted(NON_SPAWNABLE_MONSTER_LOCATION_IDS & monster_ids):
        locator_id = f"locator:official-rule:monster-location:{stable_part(monster_id)}"
        source_locators.setdefault(
            locator_id,
            Schema5SourceLocator(
                id=locator_id,
                source_document_id=source_id,
                source_file="Stardew Valley.dll",
                record_key="runtime-monster-spawn-audit",
            ),
        )
        slot_id = f"fact:{monster_id}:locations"
        if any(slot.id == slot_id for slot in package.fact_slots):
            continue
        slot = not_applicable_fact(
            next(entity for entity in entities if entity.id == monster_id), "locations"
        )
        package.fact_slots.append(slot)
        evidence_id = f"evidence:fact:{stable_part(slot.id)}"
        package.evidence.append(
            Schema5Evidence(
                id=evidence_id,
                source_locator_id=locator_id,
                evidence_kind="derived",
                transformation_rule="official-current-version-nonspawnable-monster-v1",
                input_claim_id=monster_id,
            )
        )
        package.claim_evidence.append(
            Schema5ClaimEvidence(slot.id, evidence_id, "fact_slot")
        )
    entities_by_id = {entity.id: entity for entity in entities}
    for monster_id in sorted(NON_COMBAT_MONSTER_DROP_IDS & monster_ids):
        slot_id = f"fact:{monster_id}:drops"
        if any(slot.id == slot_id for slot in package.fact_slots):
            continue
        locator_id = f"locator:official-rule:monster-drops:{stable_part(monster_id)}"
        source_locators.setdefault(
            locator_id,
            Schema5SourceLocator(
                id=locator_id,
                source_document_id=source_id,
                source_file="Stardew Valley.dll",
                record_key="runtime-non-combat-monster-audit",
            ),
        )
        slot = not_applicable_fact(entities_by_id[monster_id], "drops")
        package.fact_slots.append(slot)
        evidence_id = f"evidence:fact:{stable_part(slot.id)}"
        package.evidence.append(
            Schema5Evidence(
                id=evidence_id,
                source_locator_id=locator_id,
                evidence_kind="derived",
                transformation_rule="official-current-version-noncombat-monster-v1",
                input_claim_id=monster_id,
            )
        )
        package.claim_evidence.append(
            Schema5ClaimEvidence(slot.id, evidence_id, "fact_slot")
        )


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
            condition, condition_terms = shop_condition(
                offer, entity.id, slot_prefix, offer_key, by_id
            )
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
            if dynamic_reason is None and price.get("profitMargin"):
                dynamic_reason = "runtime-profit-margin"
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
            if non_coin_offer_written and not dynamic_price_written:
                # 种子只能以兑换获得（如沙漠节 2 换 1）时没有金币价格，
                # 按 big_craftable 口径标记为不适用而非未收录。
                ensure_not_applicable_purchase_slot(
                    package, entity, "seed_purchase_price", locators_by_entity.get(entity.id)
                )
            else:
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


def add_shop_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
    source_documents: dict[str, Schema5SourceDocument],
    source_locators: dict[str, Schema5SourceLocator],
    game_version: str,
) -> None:
    """商店玩家事实：地点、营业规则、店主与商品报价。

    地点来自人工复核映射（官方店主日程为证据）；营业时间按决策 02 属
    C 类（随店主日程变化），只发布规则语句，不假装固定时段；商品报价
    复用商店报价解析，条件紧邻报价。
    """
    shops = {entity.id: entity for entity in entities if entity.entity_type == "shop"}
    if not shops or not support.shops:
        return
    # 上游投影（鱼类地点、报价等）各自把新增定位写回 package；这里从当前
    # package 状态重建字典，避免用构建入口的过期局部字典覆盖它们。
    source_documents = {item.id: item for item in package.source_documents}
    source_locators = {item.id: item for item in package.source_locators}
    by_id = {entity.id: entity for entity in entities}
    resolver = ItemReferenceResolver.create(by_id)
    source = source_documents.setdefault(
        "source:official-support:shop-profiles",
        Schema5SourceDocument(
            id="source:official-support:shop-profiles",
            source_kind="official_derived",
            title="Data/Shops.json + Characters/schedules",
            game_version=game_version,
        ),
    )
    ordinals_by_slot: dict[str, int] = defaultdict(int)
    for entity_id, shop_entity in sorted(shops.items()):
        shop_id = shop_entity.game_id or entity_id.split(":", 1)[1]
        shop = support.shops.get(shop_id)
        if not isinstance(shop, dict):
            continue
        locator_id = f"locator:official-support:shop-profiles:{stable_part(entity_id)}"
        source_locators.setdefault(
            locator_id,
            Schema5SourceLocator(
                id=locator_id,
                source_document_id=source.id,
                source_file="Data/Shops.json",
                record_key=shop_id,
            ),
        )
        location_zh = shop_location_zh(shop_id)
        if location_zh is not None:
            slot_key = f"fact:{entity_id}:location"
            add_support_fact_item(
                package, entity_id, "location", "text", text_value=location_zh,
                scope_id=f"shop:{stable_part(entity_id)}", condition_set_id=None,
                ordinal=ordinals_by_slot[slot_key], locator_id=locator_id,
                transformation_rule="official-shop-location-map-v1",
            )
            ordinals_by_slot[slot_key] += 1
        owners = [owner for owner in shop.get("Owners") or [] if isinstance(owner, dict)]
        owner_name = next(
            (
                by_id[f"villager:{name}"].name_zh
                for owner in owners
                if (name := text_value(owner.get("Name")))
                and f"villager:{name}" in by_id
            ),
            None,
        )
        if owner_name is not None:
            slot_key = f"fact:{entity_id}:owner"
            owner_item = add_support_fact_item(
                package, entity_id, "owner", "text", text_value=owner_name,
                scope_id=f"shop:{stable_part(entity_id)}", condition_set_id=None,
                ordinal=ordinals_by_slot[slot_key], locator_id=locator_id,
                transformation_rule="official-shop-owner-v1",
            )
            ordinals_by_slot[slot_key] += 1
            add_support_facet(
                package,
                entity_id=entity_id,
                family="shop_owner",
                item=owner_item,
                condition_set_id=None,
                locator_id=locator_id,
                transformation_rule="official-shop-owner-v1",
            )
        shop_kind_label = classify_shop_kind(shop_id)
        if shop_kind_label is not None:
            kind_scope = f"shop-kind:{stable_part(entity_id)}"
            kind_item = add_support_fact_item(
                package, entity_id, "shop_kind", "text", text_value=shop_kind_label,
                scope_id=kind_scope, condition_set_id=None,
                ordinal=ordinals_by_slot[f"fact:{entity_id}:shop_kind"],
                locator_id=locator_id,
                transformation_rule="official-shop-kind-v1",
            )
            ordinals_by_slot[f"fact:{entity_id}:shop_kind"] += 1
            add_support_facet(
                package,
                entity_id=entity_id,
                family="shop_kind",
                item=kind_item,
                condition_set_id=None,
                locator_id=locator_id,
                transformation_rule="official-shop-kind-v1",
            )
        hours_condition_id: str | None = None
        if shop_id.startswith(("Festival_", "DesertFestival_")):
            hours_text = "仅节日当天开放"
            hours_status = "conditional"
            hours_condition_id = f"condition:shop:{stable_part(entity_id)}:hours"
            package.condition_sets.append(
                Schema5ConditionSet(
                    id=hours_condition_id,
                    completeness="complete",
                    player_summary="仅对应节日当天开放",
                )
            )
        elif shop_id in SHOP_CATALOGUE_IDS:
            ensure_support_fact_slot(
                package,
                entity_id=entity_id,
                slot_key="opening_hours",
                value_type="text",
                locator_id=locator_id,
                transformation_rule="official-shop-location-map-v1",
                status="not_applicable",
            )
            hours_text, hours_status = None, "not_applicable"
        else:
            hours_text = "随店主日程变化"
            hours_status = "dynamic_rule"
            hours_condition_id = f"condition:shop:{stable_part(entity_id)}:hours"
            package.condition_sets.append(
                Schema5ConditionSet(
                    id=hours_condition_id,
                    completeness="complete",
                    player_summary="受星期、天气与节日影响",
                )
            )
        if hours_text is not None:
            slot_key = f"fact:{entity_id}:opening_hours"
            add_support_fact_item(
                package, entity_id, "opening_hours", "text", text_value=hours_text,
                scope_id=f"shop:{stable_part(entity_id)}",
                condition_set_id=None,
                fact_condition_set_id=hours_condition_id,
                ordinal=ordinals_by_slot[slot_key], locator_id=locator_id,
                transformation_rule="official-shop-hours-rule-v1",
                status=hours_status,
            )
            ordinals_by_slot[slot_key] += 1
        offer_ordinal = 0
        for item in dictionary_list(shop.get("Items")):
            offer = shop_offer(shop_id, shop, item)
            offer_key = shop_offer_key(offer)
            scope_id = f"offer:{stable_part(offer_key)}"
            offer_locator_id = f"locator:official-support:shop-offers:{stable_part(offer_key)}"
            source_locators.setdefault(
                offer_locator_id,
                Schema5SourceLocator(
                    id=offer_locator_id,
                    source_document_id=source.id,
                    source_file="Data/Shops.json",
                    json_path=f"$.{shop_id}.Items[*]",
                    record_key=offer_key,
                ),
            )
            condition, terms = shop_condition(offer, entity_id, "shop_offer", offer_key, by_id)
            condition_id = condition.id if condition is not None else None
            if condition is not None and not any(
                existing.id == condition.id for existing in package.condition_sets
            ):
                package.condition_sets.append(condition)
                package.condition_terms.extend(terms)
            primary_refs = resolver.resolve(item.get("ItemId"))
            item_ref = next(iter(sorted(primary_refs)), None) if primary_refs else None
            if item_ref is None:
                # 纯随机商品报价不在此次波次展开；随机语义由 R4 后续处理。
                package.shop_price_diagnostics.append(
                    {"shopId": shop_id, "offerKey": offer_key, "kind": "random-only-skipped"}
                )
                continue
            slot_key = f"fact:{entity_id}:shop_offer_item"
            add_support_fact_item(
                package, entity_id, "shop_offer_item", "text", text_value=item_ref,
                scope_id=scope_id, condition_set_id=condition_id, ordinal=offer_ordinal,
                locator_id=offer_locator_id,
                transformation_rule="official-shops-to-player-facts-v1",
            )
            ordinals_by_slot[slot_key] += 1
            price = resolve_shop_offer_price(offer, by_id.get(item_ref) or shop_entity, by_id)
            currency = currency_label(offer.get("currency"))
            if price["kind"] == "coin" and currency == "金币":
                slot_key = f"fact:{entity_id}:shop_offer_price"
                add_support_fact_item(
                    package, entity_id, "shop_offer_price", "integer",
                    integer_value=price["value"], scope_id=scope_id,
                    condition_set_id=condition_id, ordinal=offer_ordinal,
                    locator_id=offer_locator_id,
                    transformation_rule="official-shop-builder-get-base-price-v1",
                    input_claim_id=str(price.get("inputClaimId") or ""),
                )
                ordinals_by_slot[slot_key] += 1
            elif price["kind"] == "currency_amount" and currency is not None:
                slot_key = f"fact:{entity_id}:shop_offer_currency"
                add_support_fact_item(
                    package, entity_id, "shop_offer_currency", "text", text_value=currency,
                    scope_id=scope_id, condition_set_id=condition_id, ordinal=offer_ordinal,
                    locator_id=offer_locator_id,
                    transformation_rule="official-shops-to-player-facts-v1",
                )
                ordinals_by_slot[slot_key] += 1
                slot_key = f"fact:{entity_id}:shop_offer_currency_amount"
                add_support_fact_item(
                    package, entity_id, "shop_offer_currency_amount", "integer",
                    integer_value=price["value"], scope_id=scope_id,
                    condition_set_id=condition_id, ordinal=offer_ordinal,
                    locator_id=offer_locator_id,
                    transformation_rule="official-shop-builder-get-base-price-v1",
                )
                ordinals_by_slot[slot_key] += 1
            elif (
                price["kind"] in {"exchange_only", "coin"}
                and offer.get("tradeItemId") is not None
            ):
                resolved_trade = resolver.resolve(offer.get("tradeItemId"))
                if len(resolved_trade) == 1:
                    slot_key = f"fact:{entity_id}:shop_offer_exchange_item_id"
                    add_support_fact_item(
                        package, entity_id, "shop_offer_exchange_item_id", "text",
                        text_value=next(iter(resolved_trade)), scope_id=scope_id,
                        condition_set_id=condition_id, ordinal=offer_ordinal,
                        locator_id=offer_locator_id,
                        transformation_rule="official-shops-to-player-facts-v1",
                    )
                    ordinals_by_slot[slot_key] += 1
                    amount = offer.get("tradeItemAmount")
                    if isinstance(amount, int) and not isinstance(amount, bool):
                        slot_key = f"fact:{entity_id}:shop_offer_exchange_amount"
                        add_support_fact_item(
                            package, entity_id, "shop_offer_exchange_amount", "integer",
                            integer_value=amount, scope_id=scope_id,
                            condition_set_id=condition_id, ordinal=offer_ordinal,
                            locator_id=offer_locator_id,
                            transformation_rule="official-shops-to-player-facts-v1",
                        )
                        ordinals_by_slot[slot_key] += 1
            elif price["kind"] == "dynamic":
                slot_key = f"fact:{entity_id}:shop_offer_price_rule"
                add_support_fact_item(
                    package, entity_id, "shop_offer_price_rule", "text",
                    text_value=PRICE_RULE_REASON_ZH.get(str(price["reason"]), "受游戏规则影响"),
                    scope_id=scope_id, condition_set_id=condition_id, ordinal=offer_ordinal,
                    locator_id=offer_locator_id,
                    transformation_rule="official-shop-builder-dynamic-price-rule-v1",
                    status="dynamic_rule",
                )
                ordinals_by_slot[slot_key] += 1
            offer_ordinal += 1
        if offer_ordinal > 0:
            add_shop_offer_count_facet(package, entity_id, offer_ordinal, locator_id)
    package.source_documents = sorted(source_documents.values(), key=lambda item: item.id)
    package.source_locators = sorted(source_locators.values(), key=lambda item: item.id)


def machine_primary_output_zh(
    machine: dict[str, object], by_id: dict[str, NormalizedEntity]
) -> str | None:
    for rule in dictionary_list(machine.get("OutputRules")):
        for out in dictionary_list(rule.get("OutputItem")):
            item_id = out.get("ItemId")
            if not isinstance(item_id, str) or not item_id:
                continue
            if item_id.startswith("FLAVORED_ITEM "):
                parts = item_id.split()
                if len(parts) >= 2:
                    return PRESERVE_OUTPUT_ZH.get(parts[1])
                continue
            reference = stable_entity_reference(item_id, by_id)
            if reference is not None:
                target = by_id.get(reference)
                if target is not None and target.name_zh:
                    return target.name_zh
    return None


def add_big_craftable_purpose_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
    source_documents: dict[str, Schema5SourceDocument],
    source_locators: dict[str, Schema5SourceLocator],
    game_version: str,
) -> None:
    """大型可制作物的「主要产物/用途」：机器数据或官方中文描述。"""
    # 与 add_shop_projections 一致：从当前 package 重建字典，避免覆盖上游投影。
    source_documents = {item.id: item for item in package.source_documents}
    source_locators = {item.id: item for item in package.source_locators}
    by_id = {entity.id: entity for entity in entities}
    source = source_documents.setdefault(
        "source:official-support:machine-outputs",
        Schema5SourceDocument(
            id="source:official-support:machine-outputs",
            source_kind="official_derived",
            title="Data/Machines.json",
            game_version=game_version,
        ),
    )
    for entity in entities:
        if entity.entity_type != "big_craftable":
            continue
        machine = support.machines.get(f"(BC){entity.game_id}")
        output_zh = (
            machine_primary_output_zh(machine, by_id)
            if isinstance(machine, dict)
            else None
        )
        if output_zh is None and entity.description_zh and entity.translation_status != "missing":
            output_zh = entity.description_zh.strip().split("。")[0][:40]
        if not output_zh or not any("\u4e00" <= char <= "\u9fff" for char in output_zh):
            continue
        locator_id = f"locator:official-support:machine-outputs:{stable_part(entity.id)}"
        source_locators.setdefault(
            locator_id,
            Schema5SourceLocator(
                id=locator_id,
                source_document_id=source.id,
                source_file=(
                    "Data/Machines.json"
                    if isinstance(machine, dict)
                    else entity.source_file
                ),
                record_key=entity.game_id or entity.id,
            ),
        )
        add_support_fact_item(
            package,
            entity.id,
            "primary_output",
            "text",
            text_value=output_zh,
            scope_id=f"machine-output:{stable_part(entity.id)}",
            condition_set_id=None,
            ordinal=0,
            locator_id=locator_id,
            transformation_rule="official-machine-output-to-player-facts-v1",
        )
    package.source_documents = sorted(source_documents.values(), key=lambda item: item.id)
    package.source_locators = sorted(source_locators.values(), key=lambda item: item.id)


def add_weapon_acquisition_projections(
    package: Schema5Package,
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
    source_documents: dict[str, Schema5SourceDocument],
    source_locators: dict[str, Schema5SourceLocator],
    game_version: str,
    official_release_binding: tuple[str, str] | None,
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
                offer, entity_id, "acquisition", offer_key, by_id
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

    add_current_version_unobtainable_weapon_facts(
        package,
        weapons,
        source_documents,
        source_locators,
        game_version,
        official_release_binding,
    )


def add_current_version_unobtainable_weapon_facts(
    package: Schema5Package,
    weapons: dict[str, NormalizedEntity],
    source_documents: dict[str, Schema5SourceDocument],
    source_locators: dict[str, Schema5SourceLocator],
    game_version: str,
    official_release_binding: tuple[str, str] | None,
) -> None:
    """Bind the version-specific negative official-code audit to acquisition."""
    expected_version, expected_dll_hash, expected_asset_hash = (
        CURRENT_VERSION_UNOBTAINABLE_WEAPON_BINDING
    )
    if game_version != expected_version or official_release_binding != (
        expected_dll_hash,
        expected_asset_hash,
    ):
        return

    source_id = "source:official-rule:current-version-unobtainable-weapons"
    source_documents.setdefault(
        source_id,
        Schema5SourceDocument(
            id=source_id,
            source_kind="official_derived",
            title="Stardew Valley.dll · current-version unobtainable weapon audit",
            game_version=game_version,
            content_hash=f"{expected_dll_hash}:{expected_asset_hash}",
        ),
    )
    for weapon_id in sorted(CURRENT_VERSION_UNOBTAINABLE_WEAPON_IDS, key=int):
        entity_id = f"weapon:{weapon_id}"
        if entity_id not in weapons:
            continue
        slot_id = f"fact:{entity_id}:acquisition"
        if any(slot.id == slot_id for slot in package.fact_slots):
            continue
        locator_id = (
            "locator:official-rule:current-version-unobtainable-weapon:"
            f"{weapon_id}"
        )
        source_locators.setdefault(
            locator_id,
            Schema5SourceLocator(
                id=locator_id,
                source_document_id=source_id,
                source_file="Stardew Valley.dll",
                record_key=(
                    "official creation/shop/reward/chest/event audit excludes "
                    f"weapon:{weapon_id}"
                ),
            ),
        )
        slot = not_applicable_fact(weapons[entity_id], "acquisition")
        package.fact_slots.append(slot)
        evidence_id = f"evidence:fact:{stable_part(slot.id)}"
        package.evidence.append(
            Schema5Evidence(
                id=evidence_id,
                source_locator_id=locator_id,
                evidence_kind="derived",
                transformation_rule="official-current-version-unobtainable-weapon-v1",
                input_claim_id=entity_id,
            )
        )
        package.claim_evidence.append(
            Schema5ClaimEvidence(slot.id, evidence_id, "fact_slot")
        )


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
        "2": (
            "击败同时带有诅咒娃娃与闹鬼骷髅状态的蝙蝠变体；该掉落为随机结果",
            "haunted_skull_cursed_doll_random_drop",
        ),
        "4": ("需要七彩碎片，并在沙漠三柱处触发规则", "prismatic_shard_desert_pillars"),
        "47": ("新存档初始工具", "new_game_start"),
        "53": ("采石场矿井尽头的黄金镰刀交互规则", "quarry_mine_golden_scythe"),
        "62": ("银河剑和 3 个银河之魂", "galaxy_sword_plus_three_souls"),
        "63": ("银河之锤和 3 个银河之魂", "galaxy_hammer_plus_three_souls"),
        "64": ("银河匕首和 3 个银河之魂", "galaxy_dagger_plus_three_souls"),
        "61": ("挑战矿井额外难度规则奖励", "mine_challenge_reward"),
        "65": (
            "在森林传送柱交付远方之石，触发对应事件奖励",
            "forest_pylon_far_away_stone_event",
        ),
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
        # 利润率设置（标准=1×，困难=1.5×）是玩家档位，不是商品定价：
        # 离线图鉴展示标准档价格，并保留「受利润率设置影响」的规则说明。
        profit_margin_only = True
    else:
        profit_margin_only = False
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
        "profitMargin": profit_margin_only,
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
        text_value=PRICE_RULE_REASON_ZH.get(reason, reason),
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
    # 种子生产器的数据触发器（!seedmaker_banned）对非作物是通配噪声；
    # 运行时规则（Object.OutputSeedMaker）只接受作物收获物（DLL 常量复核）。
    crop_harvest_item_ids = {
        f"object:{harvest_id}"
        for entity in entities
        if entity.entity_type == "crop"
        for harvest_id in [text_value(structured_attributes(entity).get("HarvestItemId"))]
        if harvest_id
    }
    for entity_id, rows in sorted(references.machine_uses.items()):
        # 戒指不会进入任何机器；`!seedmaker_banned` 通配触发器对戒指是数据级噪声。
        if by_id.get(entity_id) is not None and by_id[entity_id].entity_type == "ring":
            continue
        for ordinal, reference in enumerate(sorted(rows, key=machine_reference_key)):
            machine_id = reference.get("machineId")
            if machine_id == "(BC)25" and entity_id not in crop_harvest_item_ids:
                # 种子生产器只加工作物收获物；其余物品的该行是数据级通配噪声。
                continue
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
                (
                    f"condition:machine:{stable_part(entity_id)}:{stable_part(machine_id or 'machine')}:"
                    f"{stable_part(rule_id)}:{stable_part(trigger_id)}"
                ),
                reference,
                by_id,
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
        unique_rows = {
            usage_projection_key(reference): reference for reference in rows
        }
        for ordinal, reference in enumerate(
            sorted(unique_rows.values(), key=usage_reference_key)
        ):
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


def usage_projection_key(reference: dict[str, object]) -> tuple[str, str, str, str, str]:
    """Deduplicate identical support rows before assigning fact-item ordinals."""
    return (
        *usage_reference_key(reference),
        str(reference.get("quantity") or ""),
        str(reference.get("quality") or ""),
        str(reference.get("_source") or ""),
    )


def game_state_query_terms(
    condition_id: str,
    value: str,
    ordinal: int,
    by_id: dict[str, NormalizedEntity] | None = None,
) -> tuple[list[Schema5ConditionTerm], list[str], bool]:
    """Translate structurally valid GameStateQuery clauses without evaluating a save."""
    terms: list[Schema5ConditionTerm] = []
    summaries: list[str] = []
    for index, raw_clause in enumerate(value.split(",")):
        clause = raw_clause.strip()
        negated = clause.startswith("!")
        display = clause[1:].strip() if negated else clause
        tokens = game_state_query_tokens(display)
        if not tokens:
            return [], [], False
        predicate, arguments = tokens[0], tokens[1:]
        if predicate not in GAME_STATE_QUERY_LABELS:
            return [], [], False
        if len(arguments) not in GAME_STATE_QUERY_ARGUMENT_COUNTS.get(predicate, set()):
            return [], [], False
        if predicate == "SEASON" and any(
            argument.casefold() not in {"spring", "summer", "fall", "winter"}
            for argument in arguments
        ):
            return [], [], False
        if predicate == "LOCATION_SEASON" and any(
            argument.casefold() not in {"spring", "summer", "fall", "winter"}
            for argument in arguments[1:]
        ):
            return [], [], False
        if predicate in {"YEAR", "DAYS_PLAYED", "MINE_LOWEST_LEVEL_REACHED"} and not all(
            argument.isdigit() for argument in arguments
        ):
            return [], [], False
        # `ANY` carries a nested OR tree. Until every child is emitted with
        # its own typed predicate and grouping semantics, retain the source as
        # opaque instead of misrepresenting the parent text as complete.
        if predicate == "ANY":
            return [], [], False
        label = GAME_STATE_QUERY_LABELS[predicate]
        display_text = game_state_query_display(predicate, arguments, by_id)
        summaries.append(
            f"不满足{label}：{display_text}" if negated else f"{label}：{display_text}"
        )
        terms.append(
            Schema5ConditionTerm(
                id=(
                    f"condition-term:{stable_part(condition_id)}:"
                    f"game-state-query-{ordinal + index}"
                ),
                condition_set_id=condition_id,
                ordinal=ordinal + index,
                kind=f"game_state_query:{predicate.casefold()}",
                value_text=clause,
            )
        )
    return terms, summaries, True


def game_state_query_tokens(value: str) -> list[str] | None:
    """Read shell-like quoted query arguments and reject malformed quoting."""
    if value.count('"') % 2:
        return None
    tokens = [quoted or bare for quoted, bare in re.findall(r'"([^"]*)"|(\S+)', value)]
    return tokens if all(token.strip() for token in tokens) else None


def game_state_query_display(
    predicate: str,
    arguments: list[str],
    by_id: dict[str, NormalizedEntity] | None = None,
) -> str:
    """把谓词参数渲染为中文玩家文案（原始 GameStateQuery 不进入普通页面）。"""
    entity_index = by_id or {}
    if predicate in {"SEASON", "LOCATION_SEASON"}:
        seasons = arguments[1:] if predicate == "LOCATION_SEASON" else arguments
        return " ".join(SEASON_ZH.get(argument.casefold(), argument) for argument in seasons)
    if predicate == "DAY_OF_WEEK":
        return " ".join(
            SCHEDULE_DAY_ZH.get(argument[:3], argument) for argument in arguments
        )
    if predicate == "DAY_OF_MONTH":
        return " ".join(
            "偶数日" if argument.casefold() == "even"
            else "奇数日" if argument.casefold() == "odd"
            else f"{argument} 日"
            for argument in arguments
        )
    if predicate == "TIME":
        values = [int(argument) for argument in arguments if argument.isdigit()]
        if len(values) == len(arguments) and values:
            rendered = "–".join(f"{value // 100}:{value % 100:02d}" for value in values)
            return rendered
        return " ".join(arguments)
    if predicate == "WEATHER":
        weathers = [
            argument
            for argument in arguments
            if argument.casefold()
            not in {"here", "current", "target", "location", "host"}
        ]
        return "、".join(
            WEATHER_VALUE_ZH.get(argument.casefold(), argument) for argument in weathers
        )
    if predicate == "ITEM_CONTEXT_TAG" and len(arguments) == 2:
        # 第一个参数是查询上下文（Input/Target），玩家只关心标签本身。
        return ITEM_TAG_ZH.get(arguments[1], arguments[1])
    if predicate == "ITEM_EDIBILITY" and len(arguments) == 2:
        return ITEM_EDIBILITY_ZH.get(arguments[1].casefold(), arguments[1])
    if predicate == "RANDOM" and len(arguments) == 1:
        try:
            return f"{float(arguments[0]) * 100:g}%"
        except ValueError:
            return arguments[0]
    if predicate == "MUSEUM_DONATIONS":
        count = arguments[0]
        types = "、".join(
            MUSEUM_DONATION_TYPE_ZH.get(argument, argument) for argument in arguments[1:]
        )
        return f"{types} {count} 件"
    if predicate == "IS_PASSIVE_FESTIVAL_OPEN":
        return PASSIVE_FESTIVAL_ZH.get(arguments[0], arguments[0])
    if predicate == "PLAYER_SPECIAL_ORDER_RULE_ACTIVE" and len(arguments) == 2:
        return SPECIAL_ORDER_RULE_ZH.get(arguments[1], arguments[1])
    if predicate == "PLAYER_BASE_FARMING_LEVEL" and len(arguments) == 2:
        return f"{arguments[1]} 级"
    if predicate == "PLAYER_BASE_FISHING_LEVEL" and len(arguments) == 2:
        return f"{arguments[1]} 级"
    if predicate == "PLAYER_FARMHOUSE_UPGRADE" and len(arguments) == 2:
        return f"{arguments[1]} 级"
    if predicate == "PLAYER_HAS_ACHIEVEMENT" and len(arguments) == 2:
        achievement = entity_index.get(f"achievement:{arguments[1]}")
        if achievement is not None and achievement.name_zh:
            return achievement.name_zh
        return f"成就编号 {arguments[1]}"
    if predicate == "PLAYER_HAS_ALL_ACHIEVEMENTS":
        return "全部成就"
    if predicate == "PLAYER_HAS_TOWN_KEY":
        return "已获得"
    if predicate == "PLAYER_HAS_MAIL":
        flag = arguments[-1].strip('"')
        return MAIL_FLAG_ZH.get(flag, flag)
    if predicate == "PLAYER_HAS_CONVERSATION_TOPIC":
        topic = arguments[-1]
        return CONVERSATION_TOPIC_ZH.get(topic, topic)
    if predicate == "PLAYER_HAS_SEEN_EVENT":
        return f"事件编号 {arguments[-1]}"
    if predicate == "PLAYER_HEARTS" and len(arguments) == 3:
        who = arguments[1]
        who_zh = VILLAGER_DISPLAY_NAMES.get(who.casefold())
        if who_zh is None:
            who_zh = {"krobus": "科罗布斯", "dwarf": "矮人", "anydateable": "可婚配村民"}.get(
                who.casefold(), who
            )
        return f"{who_zh} {arguments[2]} 心"
    if predicate == "PLAYER_NPC_RELATIONSHIP":
        who = arguments[1]
        who_zh = VILLAGER_DISPLAY_NAMES.get(who.casefold())
        if who_zh is None:
            who_zh = {
                "any": "任意村民",
                "anydateable": "可婚配村民",
                "krobus": "科罗布斯",
                "dwarf": "矮人",
            }.get(who.casefold(), who)
        statuses = "、".join(
            RELATIONSHIP_STATUS_ZH.get(argument, argument) for argument in arguments[2:]
        )
        return f"{who_zh}（{statuses}）"
    if predicate == "PLAYER_HAS_ITEM" or predicate == "PLAYER_HAS_CRAFTING_RECIPE":
        # 官方数据里配方名可能带空格且不加引号（Explosive Ammo），合并余下参数。
        item = " ".join(arguments[1:])
        item_name = query_item_display_name(item, entity_index, recipe=predicate == "PLAYER_HAS_CRAFTING_RECIPE")
        return item_name if item_name is not None else item
    if predicate == "PLAYER_STAT" and len(arguments) == 3:
        stat = arguments[1]
        stat_zh = PLAYER_STAT_ZH.get(stat)
        if stat_zh is not None:
            return f"{stat_zh} {arguments[2]}"
        item_name = query_item_display_name(stat, entity_index)
        if item_name is not None:
            return f"{item_name} {arguments[2]}"
        return f"{stat} {arguments[2]}"
    if predicate == "WORLD_STATE_FIELD":
        field = WORLD_STATE_FIELD_ZH.get(arguments[0], arguments[0])
        values = " ".join(
            "是" if argument.casefold() == "true"
            else "否" if argument.casefold() == "false"
            else argument
            for argument in arguments[1:]
        )
        return f"{field} {values}"
    if predicate == "SYNCED_RANDOM" and len(arguments) in {3, 4}:
        key = arguments[1]
        key_zh = SYNCED_DAY_KEY_ZH.get(key, key)
        try:
            chance = f"{float(arguments[2]) * 100:g}%"
        except ValueError:
            chance = arguments[2]
        return f"当天同步随机：{key_zh}（{chance}）"
    if predicate == "SYNCED_CHOICE" and len(arguments) == 5:
        key = arguments[1]
        key_zh = SYNCED_DAY_KEY_ZH.get(key, key)
        return f"当天同步选择：{key_zh}（第 {arguments[4]} 档）"
    return " ".join(arguments)


def query_item_display_name(
    value: str,
    by_id: dict[str, NormalizedEntity],
    *,
    recipe: bool = False,
) -> str | None:
    """把查询里的物品/配方引用（(T)MilkPail、808、Explosive Ammo 等）解析为中文实体名。"""
    entity_type = None
    item_id = value
    if value.startswith("(") and ")" in value:
        prefix, _, rest = value[1:].partition(")")
        entity_type = {
            "O": "object",
            "BC": "big_craftable",
            "T": "tool",
            "W": "weapon",
            "F": "furniture",
            "B": "footwear",
            "TR": "trinket",
        }.get(prefix)
        item_id = rest
    if entity_type is None:
        candidate_types = ("crafting_recipe", "cooking_recipe") if recipe else ()
        candidate_types += ("object", "big_craftable", "tool", "weapon", "furniture", "footwear")
    else:
        candidate_types = (entity_type,)
    for candidate_type in candidate_types:
        for candidate in (item_id, item_id.replace(" ", "-")):
            entity = by_id.get(f"{candidate_type}:{candidate}")
            if entity is not None and entity.name_zh:
                return entity.name_zh
    return None


def opaque_rule_condition(
    package: Schema5Package,
    condition_id: str,
    reference: dict[str, object],
    by_id: dict[str, NormalizedEntity] | None = None,
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

    terms: list[Schema5ConditionTerm] = []
    summaries: list[str] = []
    complete = True
    for key, value in sorted(fields.items()):
        if key == "condition" and isinstance(value, str):
            parsed, parsed_summaries, parsed_complete = game_state_query_terms(
                condition_id, value, len(terms), by_id
            )
            terms.extend(parsed)
            summaries.extend(parsed_summaries)
            complete &= parsed_complete
            continue
        if key == "requiredTags" and isinstance(value, list) and all(
            isinstance(tag, str) and tag.strip() for tag in value
        ):
            text = ",".join(value)
            terms.append(
                Schema5ConditionTerm(
                    id=f"condition-term:{stable_part(condition_id)}:required-tags",
                    condition_set_id=condition_id,
                    ordinal=len(terms),
                    kind="required_tags",
                    value_text=text,
                )
            )
            positives: list[str] = []
            negatives: list[str] = []
            unknown_tags: list[str] = []
            for tag in value:
                negated = tag.startswith("!")
                resolved = ITEM_TAG_ZH.get(tag[1:] if negated else tag)
                if resolved is None:
                    unknown_tags.append(tag)
                elif negated:
                    negatives.append(resolved)
                else:
                    positives.append(resolved)
            if positives:
                summaries.append(f"输入须为：{'、'.join(positives)}")
            if negatives:
                summaries.append(f"排除：{'、'.join(negatives)}")
            if unknown_tags:
                summaries.append("输入限制：另有未识别标签要求")
                complete = False
            continue
        if (
            key in {"requiredCount", "minDepth", "maxDepth", "minTime", "maxTime"}
            and type(value) is int
        ):
            terms.append(
                Schema5ConditionTerm(
                    id=f"condition-term:{stable_part(condition_id)}:{stable_part(key)}",
                    condition_set_id=condition_id,
                    ordinal=len(terms),
                    kind=key,
                    value_integer=value,
                )
            )
            label = {
                "requiredCount": "所需数量",
                "minDepth": "起始层",
                "maxDepth": "结束层",
                "minTime": "起始时间",
                "maxTime": "结束时间",
            }[key]
            summaries.append(f"{label}：{value}")
            continue
        complete = False

    original_text = None if complete else json.dumps(fields, ensure_ascii=False, sort_keys=True)
    package.condition_sets.append(
        Schema5ConditionSet(
            id=condition_id,
            completeness="complete" if complete else "opaque",
            player_summary="；".join(summaries) or "官方规则受游戏条件限制",
            original_text=original_text,
        )
    )
    package.condition_terms.extend(terms)
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
    condition_set_id: str | None = None,
) -> str:
    slot_id = f"fact:{entity_id}:{slot_key}"
    existing = next((slot for slot in package.fact_slots if slot.id == slot_id), None)
    if existing is not None:
        # A fixed quote can coexist with another runtime-dependent quote. The
        # fixed quote is the main answer; the dynamic offer remains in its
        # companion ``*_price_rule`` slot. Upgrade the placeholder dynamic
        # core slot so later integer quote items retain the typed contract.
        if existing.status == "dynamic_rule" and status == "fixed":
            package.fact_slots[package.fact_slots.index(existing)] = replace(
                existing,
                status="fixed",
                value_type=value_type,
                condition_set_id=condition_set_id,
            )
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
            condition_set_id=condition_set_id,
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
    fact_condition_set_id: str | None = None,
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
        condition_set_id=fact_condition_set_id,
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


def add_shop_offer_count_facet(
    package: Schema5Package,
    entity_id: str,
    offer_count: int,
    locator_id: str,
) -> None:
    """商店商品数作为浏览 facet（列表卡显示「N 件商品」）。

    facet 证据直接以事实槽为输入 claim（商品项本身已有事实证据），
    避免引入不存在的 fact_item claim。
    """
    family = "shop_offer_count"
    group_id = f"facet-group:{entity_id}:{family}"
    package.facet_groups.append(
        Schema5FacetGroup(group_id, entity_id, family, "fixed")
    )
    facet_id = f"facet:{entity_id}:{family}:count"
    package.facets.append(
        Schema5Facet(
            id=facet_id,
            group_id=group_id,
            scope_family=family,
            scope_id=f"shop:{stable_part(entity_id)}",
            value_type="integer",
            integer_value=offer_count,
            claim_status="fixed",
        )
    )
    evidence_id = f"evidence:facet:{stable_part(facet_id)}"
    package.evidence.append(
        Schema5Evidence(
            id=evidence_id,
            source_locator_id=locator_id,
            evidence_kind="derived",
            transformation_rule="official-shop-offers-to-browse-facet-v1",
            input_claim_id=f"fact:{entity_id}:shop_offer_item",
        )
    )
    package.claim_evidence.append(Schema5ClaimEvidence(facet_id, evidence_id, "facet"))


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


def price_modifier_condition_terms(
    condition_id: str,
    key: str,
    modifiers: object,
    ordinal: int,
    by_id: dict[str, NormalizedEntity] | None = None,
) -> tuple[list[Schema5ConditionTerm], list[str], bool]:
    """Represent official modifier rows without pretending random values are fixed."""
    if not isinstance(modifiers, list) or not modifiers:
        return [], [], False
    terms: list[Schema5ConditionTerm] = []
    summaries: list[str] = []
    for index, modifier in enumerate(modifiers):
        if not isinstance(modifier, dict):
            return [], [], False
        modification = modifier.get("Modification")
        amount = modifier.get("Amount")
        random_amount = modifier.get("RandomAmount")
        condition = modifier.get("Condition")
        if (
            not isinstance(modification, str)
            or not modification
            or not isinstance(amount, int | float)
            or isinstance(amount, bool)
            or (
                random_amount is not None
                and (
                    not isinstance(random_amount, list)
                    or not all(
                        isinstance(value, int | float) and not isinstance(value, bool)
                        for value in random_amount
                    )
                )
            )
            or (condition is not None and not isinstance(condition, str))
        ):
            return [], [], False
        terms.append(
            Schema5ConditionTerm(
                id=(
                    f"condition-term:{stable_part(condition_id)}:"
                    f"{stable_part(key)}-modifier-{index}"
                ),
                condition_set_id=condition_id,
                ordinal=ordinal + len(terms),
                kind="price_modifier",
                value_text=json.dumps(modifier, ensure_ascii=False, sort_keys=True),
            )
        )
        scope_zh = PRICE_MODIFIER_SCOPE_ZH.get(key, key)
        mode_zh = PRICE_MODIFIER_MODE_ZH.get(modification, modification)
        summaries.append(f"{scope_zh}：{mode_zh} {amount}")
        if random_amount:
            summaries.append("价格修正随机取值")
        if condition:
            parsed, parsed_summaries, parsed_complete = game_state_query_terms(
                condition_id, condition, ordinal + len(terms), by_id
            )
            if not parsed_complete:
                return [], [], False
            terms.extend(parsed)
            summaries.extend(parsed_summaries)
    return terms, summaries, True


def shop_condition(
    offer: dict[str, object],
    entity_id: str,
    slot_prefix: str,
    offer_key: str,
    by_id: dict[str, NormalizedEntity] | None = None,
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
    terms: list[Schema5ConditionTerm] = []
    summaries: list[str] = []
    complete = True
    for key, value in sorted(fields.items()):
        if key in {"condition", "perItemCondition"} and isinstance(value, str):
            parsed, parsed_summaries, parsed_complete = game_state_query_terms(
                condition_id, value, len(terms), by_id
            )
            if parsed_complete:
                terms.extend(parsed)
                summaries.extend(parsed_summaries)
                continue
        if key in {"priceModifiers", "shopPriceModifiers"}:
            parsed, parsed_summaries, parsed_complete = price_modifier_condition_terms(
                condition_id, key, value, len(terms), by_id
            )
            if parsed_complete:
                terms.extend(parsed)
                summaries.extend(parsed_summaries)
                continue
        complete = False
        terms.append(
            Schema5ConditionTerm(
                id=f"condition-term:{stable_part(condition_id)}:{stable_part(key)}",
                condition_set_id=condition_id,
                ordinal=len(terms),
                kind="rule",
                value_text=(
                    value
                    if isinstance(value, str)
                    else json.dumps(value, ensure_ascii=False, sort_keys=True)
                ),
            )
        )
    return (
        Schema5ConditionSet(
            id=condition_id,
            completeness="complete" if complete else "opaque",
            player_summary=(
                "；".join(summaries)
                if complete
                else "商店报价受游戏条件或价格规则限制"
            ),
            original_text=(
                None
                if complete
                else json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
        # 稳定键保留实体 id；玩家文案在 fish_condition 里按包内实体解析为中文名。
        result.setdefault(fish_id, []).append(
            {
                "locationId": location_id,
                "areaId": "mine",
                "chance": base_chance,
                "minDepth": min_depth,
                "maxDepth": max_depth,
                "fishingLevelChance": level_chance,
                "baitHint": fish_id,
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
    by_id: dict[str, NormalizedEntity] | None = None,
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
            localized = " ".join(
                SEASON_ZH.get(item.casefold(), item)
                for item in text.split(",")
                if item.strip()
            )
            terms.append(
                Schema5ConditionTerm(
                    term_id, condition_id, len(terms), "season", value_text=text
                )
            )
            summaries.append(f"季节：{localized}")
        elif key == "condition" and isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            parsed, parsed_summaries, parsed_complete = game_state_query_terms(
                condition_id, text, len(terms), by_id
            )
            if parsed_complete:
                terms.extend(parsed)
                summaries.extend(parsed_summaries)
            else:
                terms.append(
                    Schema5ConditionTerm(
                        term_id, condition_id, len(terms), "rule", value_text=text
                    )
                )
                summaries.append("游戏条件：另有未识别限制")
                unparsed = True
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
            target = (by_id or {}).get(value)
            label = target.name_zh if target is not None and target.name_zh else value
            summaries.append(f"针对性鱼饵：{label}")
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
            display = (
                "不限"
                if key == "maxDistanceFromShore" and value == -1
                else (
                    "无等级要求"
                    if key == "minFishingLevel" and value == 0
                    else str(value)
                )
            )
            summaries.append(f"{recognized[key]}：{display}")
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
        sort_key=entity_sort_key(entity),
    )


def to_card(entity: NormalizedEntity) -> Schema5EntityCard:
    return Schema5EntityCard(
        entity_id=entity.id,
        identity_summary=entity.description_zh or entity.description_en,
        category_label=entity.category,
        sort_key=entity_sort_key(entity),
    )


def entity_sort_key(entity: NormalizedEntity) -> str:
    """默认按中文名排序；商店按性质优先级前缀，让普通商店排在节日商店前。"""
    name = entity.name_zh or entity.id
    if entity.entity_type != "shop":
        return name
    shop_id = entity.game_id or entity.id.split(":", 1)[1]
    kind = classify_shop_kind(shop_id)
    priority = SHOP_KIND_PRIORITY.get(kind, 2)
    return f"{priority:02d}-{name}"


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
        if monster_id in by_id and monster_id not in NON_COMBAT_MONSTER_DROP_IDS:
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
        if (
            monster.entity_type != "monster"
            or monster.id in NON_COMBAT_MONSTER_DROP_IDS
        ):
            continue
        attributes = structured_attributes(monster)
        raw_locations = attributes.get("Locations")
        if isinstance(raw_locations, list):
            localized_locations = [
                FISHING_LOCATION_ZH.get(str(item).strip())
                for item in raw_locations
                if str(item).strip()
            ]
            if localized_locations and all(localized_locations):
                fixed = fixed_fact(
                    monster,
                    "locations",
                    "text",
                    text_value="、".join(localized_locations),
                )
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


def recipe_output_reference(
    entity: NormalizedEntity,
    by_id: dict[str, NormalizedEntity],
) -> str | None:
    """配方产物的稳定实体引用；官方声明的产物类型优先于启发式猜测。"""
    if entity.entity_type not in {"cooking_recipe", "crafting_recipe"}:
        return None
    attributes = structured_attributes(entity)
    output_id = text_value(attributes.get("outputItemId"))
    if not output_id:
        return None
    entity_type_hint = attributes.get("outputEntityType")
    if isinstance(entity_type_hint, str) and f"{entity_type_hint}:{output_id}" in by_id:
        return f"{entity_type_hint}:{output_id}"
    return stable_entity_reference(attributes.get("outputItemId"), by_id)


def recipe_output_facts(
    entity: NormalizedEntity,
    by_id: dict[str, NormalizedEntity],
) -> list[Schema5FactSlot]:
    if entity.entity_type not in {"cooking_recipe", "crafting_recipe"}:
        return []
    reference = recipe_output_reference(entity, by_id)
    fact = fixed_fact(entity, "crafting_output_item_id", "text", text_value=reference)
    return [fact] if fact is not None else []


# 配方里按类别引用的材料（官方物品类别号）→ 中文玩家文案。
RECIPE_CATEGORY_INGREDIENT_ZH = {
    "-4": "任意鱼类",
    "-5": "任意蛋类",
    "-6": "任意奶类",
    "-777": "任意野生种子",
}


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
        raw_item_id = text_value(ingredient.get("itemId"))
        reference = stable_entity_reference(raw_item_id, by_id)
        if reference is None and raw_item_id in RECIPE_CATEGORY_INGREDIENT_ZH:
            # 类别材料（任意鱼类/蛋类/奶类）没有单一实体，作为文本材料保留。
            reference = raw_item_id
        quantity = ingredient.get("quantity")
        if reference is None or not isinstance(quantity, int) or quantity <= 0:
            continue
        quantities[reference] = quantities.get(reference, 0) + quantity
    for ordinal, reference in enumerate(sorted(quantities)):
        scope_id = f"recipe:{entity.id}:material:{stable_part(reference)}"
        # 类别材料直接以中文文案进入事实项；实体材料保留引用由 App 解析。
        material_text = RECIPE_CATEGORY_INGREDIENT_ZH.get(reference, reference)
        add_support_fact_item(
            package,
            entity.id,
            "crafting_material_id",
            "text",
            text_value=material_text,
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
        output_id = recipe_output_reference(recipe, by_id)
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
            unlock = unlock_label(
                structured_attributes(recipe).get("UnlockCondition") or "default", by_id
            )
            if unlock is not None:
                add_support_fact_item(
                    package,
                    entity.id,
                    "unlock",
                    "text",
                    text_value=unlock,
                    scope_id=f"recipe-output:{stable_part(recipe.id)}:unlock",
                    condition_set_id=None,
                    ordinal=0,
                    locator_id=locator_id,
                    transformation_rule="official-recipe-unlock-to-player-facts-v1",
                )
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


QUEST_TYPE_ZH = {
    "Basic": "基础任务",
    "Location": "剧情任务",
    "ItemDelivery": "送货任务",
    "ItemHarvest": "收获任务",
    "LostItem": "寻物任务",
    "SecretLostItem": "秘密寻物任务",
    "Monster": "讨伐任务",
    "Fishing": "钓鱼任务",
    "Building": "建造任务",
    "Crafting": "制作任务",
    "Social": "社交任务",
}

SPECIAL_ORDER_DURATION_ZH = {
    "OneDay": "一天",
    "ThreeDays": "三天",
    "Week": "一周",
    "TwoWeeks": "两周",
    "Month": "一个月",
}

# 特殊订单委托人：不在可浏览村民目录中的官方 NPC 中文名
# （来自官方 Strings 本地化，与村民条目一致）。
SPECIAL_ORDER_REQUESTER_ZH = {
    "Gunther": "冈瑟",
    "Marlon": "马龙",
    "Qi": "齐先生",
    "Mr. Qi": "齐先生",
    "Morris": "莫里斯",
    "Gil": "吉尔",
    "Gus": "格斯",
}

# 收集包区域：官方 Bundles 键前缀（"Pantry/0" → "茶水间"）。
BUNDLE_AREA_ZH = {
    "pantry": "茶水间",
    "crafts room": "工艺室",
    "fish tank": "鱼缸",
    "boiler room": "锅炉房",
    "bulletin board": "布告栏",
    "abandoned joja mart": "失踪的",
    "vault": "金库",
}


def strip_runtime_tokens(value: str) -> str:
    """移除官方文本中的运行时模板令牌（{Crop:TextPlural} 等）。"""
    cleaned = re.sub(r"\{[^}]*\}", "", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ；，、")
    return cleaned


def resolve_tailoring_output_names(
    entities: list[NormalizedEntity],
    support: OfficialSupportData,
) -> list[NormalizedEntity]:
    """把裁缝配方的「编号：43」标题解析为「裁缝配方：战士头盔」等产物名。

    官方 TailoringRecipes 的 CraftedItemId 使用 (H)/(S)/(P) 前缀引用
    帽子/衬衫/裤子，名称分别来自 hats.zh-CN.json 与 Shirts/Pants 字符串表。
    """
    resolved: list[NormalizedEntity] = []
    for entity in entities:
        if entity.entity_type != "tailoring_recipe":
            resolved.append(entity)
            continue
        output = tailoring_output_reference(entity)
        output_name = tailoring_output_name_zh(output, support)
        if not output_name:
            resolved.append(entity)
            continue
        resolved.append(
            entity.model_copy(update={"name_zh": f"裁缝配方：{output_name}"})
        )
    return resolved


def tailoring_output_reference(entity: NormalizedEntity) -> str | None:
    attributes = structured_attributes(entity)
    output = text_value(attributes.get("CraftedItemId"))
    if output is not None:
        return output
    outputs = attributes.get("CraftedItemIds")
    if isinstance(outputs, list) and outputs:
        return str(outputs[0]).strip()
    return None


def tailoring_output_name_zh(
    output: str | None, support: OfficialSupportData
) -> str | None:
    if not output:
        return None
    match = re.fullmatch(r"\(([HPS])\)(\d+)", output, re.IGNORECASE)
    if match is None:
        return None
    prefix, item_id = match.group(1).upper(), match.group(2)
    if prefix == "H":
        return support.hat_name_zh(item_id)
    if prefix == "S":
        return support.shirts_zh.get(item_id)
    if prefix == "P":
        return support.pants_zh.get(item_id)
    return None


# 裁缝第一材料：几乎全部配方从布料开始（官方标签 item_cloth）。
TAILORING_BASE_TAG_ZH = {
    "item_cloth": "布料",
    "item_lucky_purple_shorts": "刘易斯紫色短裤",
}

# 第二材料的类别标签（无法解析到具体物品时使用的中文类别名）。
TAILORING_CATEGORY_TAG_ZH = {
    "category_fish": "任意鱼类",
    "category_vegetable": "任意蔬菜",
    "category_fruits": "任意水果",
    "flower_item": "任意花卉",
    "fruit_tree_item": "任意果树果实",
    "fish_crab_pot": "任意蟹笼渔获",
    "fish_ocean": "任意海洋鱼类",
}

TAILORING_SEASON_TAG_ZH = {
    "spring": "春季作物",
    "summer": "夏季作物",
    "fall": "秋季作物",
    "winter": "冬季作物",
}


def tailoring_facts(
    entity: NormalizedEntity,
    attributes: dict[str, Any],
    by_id: dict[str, NormalizedEntity] | None,
) -> list[Schema5FactSlot]:
    """裁缝配方：所需材料与产物。

    材料标签优先解析为已发布物品的中文名（游戏隐式 item_<名称> 标签），
    类别/季节标签使用固定中文类别；产物名沿用标题解析结果。
    """
    facts: list[Schema5FactSlot] = []
    first_tags = attributes.get("FirstItemTags")
    second_tags = attributes.get("SecondItemTags")
    materials: list[str] = []
    if isinstance(first_tags, list):
        materials.extend(
            tailoring_tag_label(tag, by_id or {})
            for tag in first_tags
        )
    if isinstance(second_tags, list):
        materials.extend(
            tailoring_tag_label(tag, by_id or {})
            for tag in second_tags
        )
    materials = [name for name in materials if name]
    if materials:
        facts.append(
            fixed_fact(
                entity,
                "tailoring_materials",
                "text",
                text_value=" + ".join(materials),
            )
        )
    return facts


def tailoring_tag_label(
    tag: object, by_id: dict[str, NormalizedEntity]
) -> str | None:
    value = str(tag or "").strip()
    if not value:
        return None
    if value in TAILORING_BASE_TAG_ZH:
        return TAILORING_BASE_TAG_ZH[value]
    if value in TAILORING_CATEGORY_TAG_ZH:
        return TAILORING_CATEGORY_TAG_ZH[value]
    if value.startswith("season_"):
        season = value[len("season_"):]
        return TAILORING_SEASON_TAG_ZH.get(season)
    if value.startswith("item_"):
        key = value[len("item_"):].replace("_", " ").casefold()
        for candidate in by_id.values():
            if candidate.entity_type != "object":
                continue
            internal = (candidate.internal_name or "").strip()
            if internal and internal.casefold() == key:
                return candidate.name_zh
            compact = re.sub(r"[^a-z0-9]", "", internal.casefold())
            if compact and compact == re.sub(r"[^a-z0-9]", "", key):
                return candidate.name_zh
    return None


def lost_item_quest_parts_attrs(
    attributes: dict[str, Any], by_id: dict[str, NormalizedEntity]
) -> tuple[str | None, str | None]:
    """从官方 questLocation（"Abigail (O)191 100 129"）解析物品与委托人中文名。"""
    location = text_value(attributes.get("questLocation"))
    if not location:
        return None, None
    match = re.match(r"^([A-Za-z][\w .'-]*) \(O\)(\d+)\b", location)
    if match is None:
        return None, None
    villager_key = match.group(1)
    item_id = match.group(2)
    villager = by_id.get(f"villager:{villager_key}")
    villager_name = (
        villager.name_zh if villager is not None and villager.name_zh else villager_key
    )
    item = by_id.get(f"object:{item_id}")
    item_name = item.name_zh if item is not None and item.name_zh else item_id
    return item_name, villager_name


def quest_facts(
    entity: NormalizedEntity,
    attributes: dict[str, Any],
    by_id: dict[str, NormalizedEntity] | None = None,
) -> list[Schema5FactSlot]:
    """任务：类型/目标/奖励/可重复。目标与描述来自官方本地的中文本地化记录。

    探险家公会讨伐任务（MonsterSlayerQuests）使用另一套字段：Targets 是
    怪物列表，Count 是目标数量，RewardItemPrice 是金币奖励。
    秘密寻物任务（SecretLostItem）官方占位标题/目标为省略号，从
    questLocation 解析「把<物品>交给<村民>」。
    """
    quest_type = text_value(attributes.get("questType"))
    facts: list[Schema5FactSlot] = []
    if quest_type is not None:
        facts.append(
            fixed_fact(
                entity,
                "quest_type",
                "text",
                text_value=QUEST_TYPE_ZH.get(quest_type, quest_type),
            )
        )
    else:
        targets = attributes.get("Targets")
        count = attributes.get("Count")
        if isinstance(targets, list) and targets:
            facts.append(
                fixed_fact(
                    entity,
                    "quest_type",
                    "text",
                    text_value="讨伐任务",
                )
            )
            count_text = f"共 {count} 只" if isinstance(count, int) and count > 0 else ""
            facts.append(
                fixed_fact(
                    entity,
                    "quest_objective",
                    "text",
                    text_value=(
                        f"消灭{count_text}目标怪物（{targets_label(targets, by_id or {})}）"
                    ),
                )
            )
        reward_price = attributes.get("RewardItemPrice")
        if isinstance(reward_price, int) and reward_price > 0:
            facts.append(
                fixed_fact(
                    entity,
                    "quest_reward",
                    "text",
                    text_value=f"{reward_price} 金币",
                )
            )
    objective = text_value(attributes.get("questObjective"))
    if objective is None or not objective.strip(" .…·"):
        item_name, villager_name = lost_item_quest_parts_attrs(
            attributes, by_id or {}
        )
        if item_name is not None and villager_name is not None:
            objective = f"把{item_name}交给{villager_name}"
    if objective is not None and objective.strip(" .…·"):
        facts.append(fixed_fact(entity, "quest_objective", "text", text_value=objective))
    reward_parts = []
    reward_item = text_value(attributes.get("questRewardItemId"))
    if reward_item is not None and reward_item != "-1":
        reward_parts.append(f"物品奖励（{reward_item}）")
    reward_gold = attributes.get("questRewardGold")
    if isinstance(reward_gold, int) and reward_gold > 0:
        reward_parts.append(f"{reward_gold} 金币")
    if reward_parts:
        facts.append(
            fixed_fact(entity, "quest_reward", "text", text_value="、".join(reward_parts))
        )
    repeatable = attributes.get("questRepeatable")
    if isinstance(repeatable, bool):
        facts.append(
            fixed_fact(
                entity,
                "quest_repeatable",
                "boolean",
                boolean_value=repeatable,
            )
        )
    return facts


def targets_label(targets: list[object], by_id: dict[str, NormalizedEntity]) -> str:
    """讨伐目标怪物列表的中文标签（去重）。"""
    names: list[str] = []
    seen: set[str] = set()
    for target in targets:
        value = str(target).strip()
        if not value:
            continue
        reference = f"monster:{value.replace(' ', '-')}"
        target_entity = by_id.get(reference)
        label = (
            target_entity.name_zh
            if target_entity is not None and target_entity.name_zh
            else value
        )
        if label in seen:
            continue
        seen.add(label)
        names.append(label)
    return "、".join(names[:6]) + ("…" if len(names) > 6 else "")


def achievement_facts(
    entity: NormalizedEntity, attributes: dict[str, Any]
) -> list[Schema5FactSlot]:
    """成就：解锁条件与隐藏标记。描述即玩家可见的解锁条件。"""
    facts: list[Schema5FactSlot] = []
    description = text_value(attributes.get("achievementDescription"))
    if description is not None:
        facts.append(
            fixed_fact(
                entity, "achievement_description", "text", text_value=description
            )
        )
    secret = attributes.get("achievementSecret")
    if isinstance(secret, bool):
        facts.append(
            fixed_fact(
                entity, "achievement_secret", "boolean", boolean_value=secret
            )
        )
    return facts


def bundle_facts(
    entity: NormalizedEntity,
    attributes: dict[str, Any],
    by_id: dict[str, NormalizedEntity] | None,
) -> list[Schema5FactSlot]:
    """收集包：区域与所需物品。"""
    facts: list[Schema5FactSlot] = []
    area = bundle_area_label(entity)
    if area is not None:
        facts.append(fixed_fact(entity, "bundle_area", "text", text_value=area))
    ingredients = attributes.get("BundleIngredients")
    if isinstance(ingredients, list) and ingredients:
        names = [
            bundle_ingredient_label(item, by_id or {})
            for item in ingredients
            if isinstance(item, dict)
        ]
        names = [name for name in names if name]
        if names:
            facts.append(
                fixed_fact(
                    entity, "bundle_ingredients", "text", text_value="、".join(names)
                )
            )
    rewards = attributes.get("BundleRewards")
    if isinstance(rewards, list) and rewards:
        labels = [
            bundle_reward_label(item, by_id or {})
            for item in rewards
            if isinstance(item, dict)
        ]
        labels = [label for label in labels if label]
        if labels:
            facts.append(
                fixed_fact(entity, "bundle_reward", "text", text_value="、".join(labels))
            )
    return facts


def bundle_area_label(entity: NormalizedEntity) -> str | None:
    key = (entity.game_id or "").split("/", maxsplit=1)[0].strip().casefold()
    label = BUNDLE_AREA_ZH.get(key)
    if label is not None:
        return label
    # 社区中心房间级收集包（工艺室/茶水间/鱼缸/锅炉房/布告栏）：
    # 官方 RandomBundles 的 AreaName 即区域名。
    area_name = text_value(structured_attributes(entity).get("AreaName"))
    if area_name is not None:
        return BUNDLE_AREA_ZH.get(area_name.strip().casefold()) or area_name
    return None


def bundle_ingredient_label(
    item: dict[str, object], by_id: dict[str, NormalizedEntity]
) -> str | None:
    item_id = text_value(item.get("itemId"))
    if item_id is None:
        return None
    quantity = item.get("quantity")
    if item_id == "-1":
        # 官方金库收集包用 -1 表示金币（quantity 即金额）。
        if isinstance(quantity, int) and quantity > 1:
            return f"{quantity} 金币"
        return "金币"
    reference = f"object:{item_id}"
    target = by_id.get(reference)
    name = target.name_zh if target is not None else item_id
    suffix = f"×{quantity}" if isinstance(quantity, int) and quantity > 1 else ""
    quality = item.get("quality")
    quality_label = BUNDLE_QUALITY_ZH.get(quality)
    if quality_label:
        suffix += f"（{quality_label}）"
    return f"{name}{suffix}"


# 官方品质码 → 中文（1=银星，2=金星，4=铱星）。
BUNDLE_QUALITY_ZH = {1: "银星", 2: "金星", 4: "铱星"}


def bundle_reward_label(
    item: dict[str, object], by_id: dict[str, NormalizedEntity]
) -> str | None:
    """收集包奖励的中文名（官方奖励令牌类型 O/BO/R → 对应实体类型）。"""
    item_id = text_value(item.get("itemId"))
    if item_id is None:
        return None
    kind = str(item.get("type") or "O").casefold()
    prefix = {"o": "object", "bo": "big_craftable", "r": "ring"}.get(kind, "object")
    target = by_id.get(f"{prefix}:{item_id}")
    name = target.name_zh if target is not None and target.name_zh else item_id
    quantity = item.get("quantity")
    suffix = f"×{quantity}" if isinstance(quantity, int) and quantity > 1 else ""
    return f"{name}{suffix}"


# 官方 BuffEffects 字段 → 中文增益名（1.6 Objects.json Buffs/CustomAttributes）。
FOOD_BUFF_ZH = {
    "FarmingLevel": "耕种",
    "FishingLevel": "钓鱼",
    "MiningLevel": "采矿",
    "ForagingLevel": "采集",
    "LuckLevel": "幸运",
    "CombatLevel": "战斗",
    "MaxStamina": "体力上限",
    "MagneticRadius": "磁铁范围",
    "Speed": "速度",
    "Defense": "防御",
    "Attack": "攻击",
    "AttackMultiplier": "攻击倍率",
    "Immunity": "免疫",
    "KnockbackMultiplier": "击退",
    "WeaponSpeedMultiplier": "武器速度",
    "CriticalChanceMultiplier": "暴击率",
    "CriticalPowerMultiplier": "暴击威力",
    "WeaponPrecisionMultiplier": "武器精准",
}

# BuffEffects 显示顺序（技能等级 → 体力/磁铁 → 战斗数值）。
FOOD_BUFF_ORDER = [
    "FarmingLevel",
    "FishingLevel",
    "MiningLevel",
    "ForagingLevel",
    "LuckLevel",
    "CombatLevel",
    "MaxStamina",
    "MagneticRadius",
    "Speed",
    "Defense",
    "Attack",
    "AttackMultiplier",
    "Immunity",
    "KnockbackMultiplier",
    "WeaponSpeedMultiplier",
    "CriticalChanceMultiplier",
    "CriticalPowerMultiplier",
    "WeaponPrecisionMultiplier",
]

# 食用恢复公式特例（1.6.15 Object.staminaRecoveredOnConsumption /
# healthRecoveredOnConsumption 的官方硬编码）。
STAR_FOOD_ITEM_ID = "434"  # 星之果实：恢复全部体力
LIFE_ELIXIR_ITEM_ID = "773"  # 生命药剂：恢复全部生命
ENERGY_TONIC_ITEM_ID = "349"  # 体力药剂：只恢复体力
BUG_STEAK_ITEM_ID = "874"  # 虫肉扒：生命按体力的 68% 恢复


def _food_stamina_health(edibility: int, item_id: str) -> tuple[int | None, int | None]:
    """基础品质下官方恢复量：体力 = ceil(食用值×2.5)，生命 = 体力×0.45。"""
    if item_id == STAR_FOOD_ITEM_ID:
        return 999, None
    if item_id == LIFE_ELIXIR_ITEM_ID:
        return None, 999
    if item_id == ENERGY_TONIC_ITEM_ID:
        return math.ceil(edibility * 2.5), None
    stamina = math.ceil(edibility * 2.5)
    if item_id == BUG_STEAK_ITEM_ID:
        return stamina, int(stamina * 0.68)
    return stamina, int(stamina * 0.45)


def _food_buff_duration_label(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} 分钟"
    if minutes % 60 == 0:
        return f"{minutes // 60} 小时"
    return f"{minutes // 60} 小时 {minutes % 60} 分钟"


def _buff_value_label(value: object) -> str:
    if isinstance(value, bool):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if abs(number - round(number)) < 1e-9:
        number = round(number)
    return f"{number:g}"


def _buff_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def food_effect_facts(
    entity: NormalizedEntity,
    attributes: dict[str, Any],
    item_id: str | None = None,
) -> list[Schema5FactSlot]:
    """食物/饮品：恢复量与增益（来自官方 Edibility/Buffs，公式与 1.6.15 游戏一致）。"""
    facts: list[Schema5FactSlot] = []
    edibility = attributes.get("Edibility")
    if not isinstance(edibility, int) or isinstance(edibility, bool) or edibility <= 0:
        return facts
    if item_id is None:
        item_id = (entity.game_id or "").split("/", maxsplit=1)[0].strip()
    stamina, health = _food_stamina_health(edibility, item_id)
    parts: list[str] = []
    if stamina == 999:
        parts.append("恢复全部体力")
    elif stamina is not None:
        parts.append(f"恢复 {stamina} 体力")
    if health == 999:
        parts.append("恢复全部生命")
    elif health is not None:
        parts.append(f"恢复 {health} 生命")
    if parts:
        facts.append(
            fixed_fact(entity, "edibility", "text", text_value="、".join(parts))
        )
    buffs = attributes.get("Buffs")
    if not isinstance(buffs, list) or not buffs:
        return facts
    labels: list[str] = []
    for buff in buffs:
        if not isinstance(buff, dict):
            continue
        raw = buff.get("CustomAttributes")
        if not isinstance(raw, dict):
            continue
        values = [
            (key, raw[key])
            for key in FOOD_BUFF_ORDER
            if key in raw and _buff_number(raw[key]) not in (None, 0)
        ]
        if not values:
            continue
        text = "、".join(
            f"{FOOD_BUFF_ZH[key]}+{_buff_value_label(value)}" for key, value in values
        )
        duration = buff.get("Duration")
        if isinstance(duration, int) and duration > 0:
            text += f"（持续 {_food_buff_duration_label(duration)}）"
        labels.append(text)
    if labels:
        facts.append(
            fixed_fact(entity, "food_buffs", "text", text_value="；".join(labels))
        )
    return facts


def recipe_effect_facts(
    entity: NormalizedEntity,
    attributes: dict[str, Any],
    by_id: dict[str, NormalizedEntity] | None,
) -> list[Schema5FactSlot]:
    """料理配方：成品菜肴的恢复量与增益（来自产出物品的官方数据）。"""
    output_id = text_value(attributes.get("outputItemId"))
    if not output_id:
        return []
    target = (by_id or {}).get(f"object:{output_id}")
    if target is None:
        return []
    return food_effect_facts(
        entity, structured_attributes(target), item_id=target.game_id
    )


# 送礼偏好层级 → 中文标签（物品详情页只展示最有价值的层级）。
GIFT_LEVEL_ZH = {"loved": "最爱", "liked": "喜欢"}


def build_item_relation_indexes(
    entities: list[NormalizedEntity],
) -> tuple[dict[str, dict[str, list[str]]], dict[str, set[str]], dict[str, dict[str, list[str]]]]:
    """物品反查索引：送礼（哪些村民最爱/喜欢它）与怪物掉落来源。

    - gift_index: itemId → {loved/liked: [村民中文名]}
    - universal_gift: itemId → {loved/liked}（Universal_* 条目，表示全体村民）
    - drop_index: itemId → {怪物中文名: [概率文案]}
    """
    by_id = {entity.id: entity for entity in entities}
    gift_index: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    universal_gift: dict[str, set[str]] = defaultdict(set)
    drop_index: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for entity in entities:
        if entity.entity_type == "villager_gift":
            tastes = entity.source_attributes.get("GiftTastes")
            if not isinstance(tastes, list):
                continue
            suffix = entity.id.split(":", 1)[1] if ":" in entity.id else ""
            is_universal = suffix.casefold().startswith("universal_")
            villager = by_id.get(f"villager:{suffix}")
            villager_name = (
                villager.name_zh if villager is not None and villager.name_zh else None
            )
            for entry in tastes:
                if not isinstance(entry, dict):
                    continue
                preference = str(entry.get("preference") or "").casefold()
                if preference not in GIFT_LEVEL_ZH:
                    continue
                items = entry.get("items")
                if not isinstance(items, list):
                    continue
                for raw in items:
                    item_id = str(raw or "").strip()
                    if not item_id or item_id.startswith("-"):
                        continue
                    if is_universal:
                        universal_gift[item_id].add(preference)
                    elif villager_name:
                        names = gift_index[item_id][preference]
                        if villager_name not in names:
                            names.append(villager_name)
        elif entity.entity_type == "drop":
            attrs = entity.source_attributes
            item_id = str(attrs.get("itemId") or "").strip()
            if not item_id or item_id.startswith("-"):
                continue
            monster_id = str(attrs.get("monsterId") or "").strip().replace(" ", "-")
            monster = by_id.get(f"monster:{monster_id}")
            monster_name = (
                monster.name_zh if monster is not None and monster.name_zh else monster_id
            )
            chance = drop_chance(entity)
            if chance:
                drop_index[item_id][monster_name].append(chance)
    return gift_index, universal_gift, drop_index


def gift_liker_facts(
    entity: NormalizedEntity,
    gift_index: dict[str, dict[str, list[str]]] | None,
    universal_gift: dict[str, set[str]] | None,
) -> list[Schema5FactSlot]:
    """物品：哪些村民最爱/喜欢它（来自官方 NPCGiftTastes 反查）。"""
    if gift_index is None or universal_gift is None:
        return []
    item_id = (entity.game_id or "").split("/", maxsplit=1)[0].strip()
    if not item_id:
        return []
    parts: list[str] = []
    for level in ("loved", "liked"):
        if item_id in universal_gift and level in universal_gift[item_id]:
            parts.append(f"{GIFT_LEVEL_ZH[level]}：所有人")
            continue
        names = gift_index.get(item_id, {}).get(level)
        if names:
            parts.append(f"{GIFT_LEVEL_ZH[level]}：{'、'.join(names)}")
    if not parts:
        return []
    return [fixed_fact(entity, "gift_likers", "text", text_value="；".join(parts))]


def drop_source_facts(
    entity: NormalizedEntity,
    drop_index: dict[str, dict[str, list[str]]] | None,
) -> list[Schema5FactSlot]:
    """物品：哪些怪物会掉落它（反查掉落记录，合并同怪物的多档概率）。"""
    if drop_index is None:
        return []
    item_id = (entity.game_id or "").split("/", maxsplit=1)[0].strip()
    if not item_id:
        return []
    by_monster = drop_index.get(item_id)
    if not by_monster:
        return []
    labels: list[str] = []
    for monster_name in sorted(by_monster):
        chances = list(dict.fromkeys(by_monster[monster_name]))
        text = monster_name
        if chances:
            text += f"（{'、'.join(chances)}）"
        labels.append(text)
    return [fixed_fact(entity, "drop_sources", "text", text_value="、".join(labels))]


# 配方解锁技能 → 中文（1.6 官方 "s <skill> <level>" 格式）。
RECIPE_SKILL_ZH = {
    "farming": "耕种",
    "fishing": "钓鱼",
    "foraging": "采集",
    "mining": "采矿",
    "combat": "战斗",
    "luck": "幸运",
}

TV_SEASON_ZH = ("春季", "夏季", "秋季", "冬季")


def tv_date_label(episode: int) -> str:
    """女王的美食剧集 → 首播日期（两年 224 天循环，每周日一集）。

    与游戏 TV.getWeeklyRecipe 的 DaysPlayed%224/7 周索引一致：第 N 集在
    DaysPlayed = 7N-1（该周周日）播出（已在 wiki 的煎蛋卷/披萨/萝卜沙拉
    首播日期上验证）。
    """
    days_played = 7 * episode - 1
    year_label = "奇数年" if days_played // 112 == 0 else "偶数年"
    day_of_year = days_played % 112
    return f"{year_label}{TV_SEASON_ZH[day_of_year // 28]}{day_of_year % 28 + 1}日"


def _pond_entry_applies(entry: dict[str, object], fish_item_id: str) -> bool:
    """鱼塘产出规则是否适用于该鱼（官方 Condition 按输入鱼过滤）。"""
    condition = text_value(entry.get("Condition"))
    if not condition:
        return True
    if condition.startswith("ITEM_ID Input "):
        allowed = {
            token[3:].strip()
            for token in condition.split()[2:]
            if token.startswith("(O)")
        }
        return fish_item_id in allowed
    return True


def build_fish_pond_index(
    support: OfficialSupportData | None,
    by_id: dict[str, NormalizedEntity],
) -> dict[str, list[dict[str, object]]]:
    """鱼塘产出索引：鱼实体 ID → 官方 FishPondData 产出规则列表（按输入鱼过滤）。"""
    if support is None:
        return {}
    index: dict[str, list[dict[str, object]]] = defaultdict(list)
    for pond in support.fish_ponds:
        required_tags = {
            str(tag).strip() for tag in (pond.get("RequiredTags") or []) if str(tag).strip()
        }
        produced = pond.get("ProducedItems")
        if not isinstance(produced, list) or not produced:
            continue
        for entity_id, entity in by_id.items():
            if entity.entity_type != "fish" or not entity.game_id:
                continue
            item = by_id.get(f"object:{entity.game_id}")
            tags = tags_for_entity(item, by_id) if item else set()
            if required_tags and not required_tags.issubset(tags):
                continue
            index[entity_id].extend(
                entry
                for entry in produced
                if isinstance(entry, dict)
                and _pond_entry_applies(entry, entity.game_id)
            )
    return index


def fish_pond_facts(
    entity: NormalizedEntity,
    pond_index: dict[str, list[dict[str, object]]] | None,
    by_id: dict[str, NormalizedEntity],
) -> list[Schema5FactSlot]:
    """鱼：鱼塘产出物（人口门槛 + 物品 + 概率）。"""
    if not pond_index:
        return []
    rules = pond_index.get(entity.id)
    if not rules:
        return []
    labels: list[str] = []
    for rule in rules:
        item_id = text_value(rule.get("ItemId"))
        if not item_id:
            continue
        if item_id.startswith("(O)"):
            item_id = item_id[3:]
        target = by_id.get(f"object:{item_id}")
        name = target.name_zh if target is not None and target.name_zh else item_id
        parts = [name]
        population = rule.get("RequiredPopulation")
        if isinstance(population, int) and population > 0:
            parts.append(f"{population} 条后")
        chance = rule.get("Chance")
        if isinstance(chance, int | float) and not isinstance(chance, bool):
            parts.append(percent_label(chance * 100))
        detail = "，".join(parts[1:])
        labels.append(f"{parts[0]}（{detail}）" if detail else parts[0])
    if not labels:
        return []
    return [fixed_fact(entity, "fish_pond_outputs", "text", text_value="；".join(labels))]


def build_museum_reward_index(
    support: OfficialSupportData | None,
    by_id: dict[str, NormalizedEntity],
) -> dict[str, list[str]]:
    """博物馆捐赠奖励索引：物品 ID → 捐赠该物品获得的奖励中文名。

    只收录「捐赠单个指定物品即触发」的里程碑（TargetContextTags 全部为
    该物品的 id_o_ 标签）；按数量累计的里程碑（如古物 15 件）不挂在单件物品上。
    """
    if support is None:
        return {}
    index: dict[str, list[str]] = defaultdict(list)
    for entry in support.museum_rewards.values():
        if not isinstance(entry, dict):
            continue
        tags = entry.get("TargetContextTags")
        if not isinstance(tags, list) or not tags:
            continue
        item_ids: list[str] = []
        for tag in tags:
            if not isinstance(tag, dict):
                break
            raw = str(tag.get("Tag") or "")
            if not raw.startswith("id_o_") or tag.get("Count") != 1:
                break
            item_ids.append(raw[5:])
        else:
            if not item_ids:
                continue
            label = museum_reward_label(entry, by_id)
            if label:
                for item_id in item_ids:
                    index[item_id].append(label)
    return index


def museum_reward_label(
    entry: dict[str, object], by_id: dict[str, NormalizedEntity]
) -> str | None:
    reward_id = str(entry.get("RewardItemId") or "")
    if not reward_id:
        return None
    key = reward_id[3:] if reward_id.startswith("(") else reward_id
    prefix = {
        "(O)": "object",
        "(BC)": "big_craftable",
        "(F)": "furniture",
        "(W)": "weapon",
        "(R)": "ring",
    }.get(reward_id[:3], "object")
    target = by_id.get(f"{prefix}:{key}")
    name = target.name_zh if target is not None and target.name_zh else reward_id
    count = entry.get("RewardItemCount")
    if isinstance(count, int) and count > 1:
        return f"{name}×{count}"
    return name


def museum_reward_facts(
    entity: NormalizedEntity,
    museum_index: dict[str, list[str]] | None,
) -> list[Schema5FactSlot]:
    if not museum_index:
        return []
    item_id = (entity.game_id or "").split("/", maxsplit=1)[0].strip()
    labels = list(dict.fromkeys(museum_index.get(item_id, [])))
    if not labels:
        return []
    return [
        fixed_fact(entity, "museum_reward", "text", text_value="、".join(labels))
    ]


def build_recipe_shop_index(entities: list[NormalizedEntity]) -> dict[str, list[str]]:
    """商店配方索引：菜谱产物物品 ID → 出售该配方的商店中文名。"""
    index: dict[str, list[str]] = defaultdict(list)
    for entity in entities:
        if entity.entity_type != "shop":
            continue
        items = entity.source_attributes.get("Items")
        if not isinstance(items, list):
            continue
        shop_name = entity.name_zh or entity.id
        for item in items:
            if not isinstance(item, dict) or not item.get("IsRecipe"):
                continue
            raw = str(item.get("ItemId") or "").strip()
            if raw.startswith("(O)"):
                raw = raw[3:]
            if raw:
                index[raw].append(shop_name)
    return index


# 官方 Furniture.json 类型 → 中文（家具详情「类型」）。
FURNITURE_TYPE_ZH = {
    "decor": "装饰",
    "painting": "挂画",
    "rug": "地毯",
    "table": "桌子",
    "long table": "长桌",
    "chair": "椅子",
    "armchair": "扶手椅",
    "couch": "沙发",
    "bench": "长凳",
    "bed": "床",
    "bed double": "双人床",
    "bed child": "儿童床",
    "lamp": "灯具",
    "sconce": "壁灯",
    "torch": "火炬",
    "bookcase": "书架",
    "dresser": "梳妆台",
    "fireplace": "壁炉",
    "window": "窗户",
    "fishtank": "鱼缸",
    "randomized_plant": "植物",
    "other": "其他",
}


def furniture_kind_facts(
    entity: NormalizedEntity, attributes: dict[str, Any]
) -> list[Schema5FactSlot]:
    """家具：官方类型中文名（椅子/桌子/床/地毯/挂画…）。"""
    raw = text_value(attributes.get("furnitureType"))
    if raw is None:
        return []
    label = FURNITURE_TYPE_ZH.get(raw.strip().casefold())
    if label is None:
        return []
    return [fixed_fact(entity, "furniture_kind", "text", text_value=label)]


def crop_harvest_quantity_facts(
    entity: NormalizedEntity, attributes: dict[str, Any]
) -> list[Schema5FactSlot]:
    """作物：每次收获数量（官方 HarvestMin/MaxStack；部分条目 max 反置按 min）。"""
    minimum = int_value(attributes.get("HarvestMinStack"))
    maximum = int_value(attributes.get("HarvestMaxStack"))
    if minimum is None or maximum is None:
        return []
    if maximum > minimum:
        return [
            fixed_fact(
                entity,
                "harvest_quantity",
                "text",
                text_value=f"每次收获 {minimum}–{maximum} 个",
            )
        ]
    if maximum == minimum == 1:
        return []
    return [
        fixed_fact(
            entity, "harvest_quantity", "text", text_value=f"每次收获 {minimum} 个"
        )
    ]


def recipe_source_facts(
    entity: NormalizedEntity,
    attributes: dict[str, Any],
    support: OfficialSupportData | None,
    by_id: dict[str, NormalizedEntity] | None,
    shop_index: dict[str, list[str]] | None,
) -> list[Schema5FactSlot]:
    """配方获取方式：初始掌握 / 技能等级 / 好感邮件 / 女王的美食 / 商店购买。"""
    parts: list[str] = []
    unlock = text_value(attributes.get("UnlockCondition"))
    if unlock:
        tokens = unlock.split()
        first = tokens[0].casefold() if tokens else ""
        if first == "default":
            parts.append("初始掌握")
        elif first == "f" and len(tokens) >= 3:
            villager = (by_id or {}).get(f"villager:{tokens[1]}")
            name = (
                villager.name_zh
                if villager is not None and villager.name_zh
                else tokens[1]
            )
            parts.append(f"与{name}好感度{tokens[2]}心（邮件获得）")
        elif first == "s" and len(tokens) >= 3:
            skill = RECIPE_SKILL_ZH.get(tokens[1].casefold(), tokens[1])
            parts.append(f"{skill}等级 {tokens[2]}")
    if support is not None:
        episode = support.cooking_channel_episodes.get(str(entity.game_id or ""))
        if episode is not None:
            parts.append(f"女王的美食（{tv_date_label(episode)}）")
    output_id = text_value(attributes.get("outputItemId"))
    if output_id and shop_index:
        shops = sorted(set(shop_index.get(output_id, [])))
        if shops:
            parts.append(f"{'、'.join(shops)}购买")
    if not parts:
        return []
    return [fixed_fact(entity, "recipe_source", "text", text_value="、".join(parts))]


def drop_facts(
    entity: NormalizedEntity,
    attributes: dict[str, Any],
    by_id: dict[str, NormalizedEntity] | None,
) -> list[Schema5FactSlot]:
    """掉落记录：概率与来源怪物。

    掉落条目本身是怪物详情「掉落详情」的数据源；这里让掉落条目
    自己的详情页也有可读内容（概率 + 掉落来源），而不是空页面。
    """
    facts: list[Schema5FactSlot] = []
    chance = attributes.get("chance")
    if isinstance(chance, str):
        try:
            chance = float(chance)
        except ValueError:
            chance = None
    if isinstance(chance, int | float) and not isinstance(chance, bool):
        facts.append(
            fixed_fact(
                entity, "drop_chance", "text", text_value=percent_label(chance * 100)
            )
        )
    raw_monster = text_value(attributes.get("monsterId"))
    if raw_monster is not None:
        monster_id = f"monster:{raw_monster.strip().replace(' ', '-')}"
        monster = (by_id or {}).get(monster_id)
        monster_name = monster.name_zh if monster is not None else raw_monster
        facts.append(
            fixed_fact(entity, "drop_source", "text", text_value=monster_name)
        )
    return facts


def special_order_facts(
    entity: NormalizedEntity,
    attributes: dict[str, Any],
    by_id: dict[str, NormalizedEntity] | None = None,
) -> list[Schema5FactSlot]:
    """特殊订单：委托人、时限与目标摘要。

    委托人从官方 Requester 解析为已发布村民的中文名；目标文本来自
    本地化后的官方描述，占位符未解析时回退到描述。
    """
    facts: list[Schema5FactSlot] = []
    requester = text_value(attributes.get("Requester"))
    if requester is not None and requester != "None":
        requester_zh = SPECIAL_ORDER_REQUESTER_ZH.get(requester)
        if requester_zh is None and by_id is not None:
            villager = by_id.get(f"villager:{requester}")
            if villager is not None and villager.name_zh:
                requester_zh = villager.name_zh
        facts.append(
            fixed_fact(
                entity, "special_order_requester", "text", text_value=requester_zh or requester
            )
        )
    duration = text_value(attributes.get("Duration"))
    if duration is not None:
        facts.append(
            fixed_fact(
                entity,
                "special_order_duration",
                "text",
                text_value=SPECIAL_ORDER_DURATION_ZH.get(duration, duration),
            )
        )
    objectives = attributes.get("Objectives")
    objective_texts: list[str] = []
    if isinstance(objectives, list):
        for item in objectives:
            if not isinstance(item, dict):
                continue
            value = text_value(item.get("Text"))
            if value and not value.startswith("[") and value not in objective_texts:
                objective_texts.append(value)
    if not objective_texts:
        # 官方 Objectives/Text 常为本地化占位符（[Willy_Text] 等），
        # 回退到解析阶段已本地化的官方描述；运行时模板令牌（{...}）
        # 属于技术占位，离线图鉴不展示。
        description = entity.description_zh or entity.description_en
        if description:
            objective_texts.append(description)
    cleaned = [
        strip_runtime_tokens(value)
        for value in objective_texts
        if strip_runtime_tokens(value)
    ]
    if cleaned:
        facts.append(
            fixed_fact(
                entity,
                "special_order_objective",
                "text",
                text_value="；".join(cleaned),
            )
        )
    rewards = attributes.get("Rewards")
    if isinstance(rewards, list) and rewards:
        labels = [
            special_order_reward_label(item, by_id or {})
            for item in rewards
            if isinstance(item, dict)
        ]
        labels = [label for label in labels if label]
        if labels:
            facts.append(
                fixed_fact(
                    entity,
                    "special_order_reward",
                    "text",
                    text_value="、".join(labels),
                )
            )
    if isinstance(attributes.get("Repeatable"), bool):
        facts.append(
            fixed_fact(
                entity,
                "special_order_repeatable",
                "boolean",
                boolean_value=attributes["Repeatable"],
            )
        )
    return facts


def special_order_reward_label(
    reward: dict[str, object], by_id: dict[str, NormalizedEntity]
) -> str | None:
    """特殊订单奖励的中文文案（金币/物品/好感度；邮件奖励不展示）。"""
    reward_type = text_value(reward.get("Type"))
    data = reward.get("Data")
    if not isinstance(data, dict):
        return None
    if reward_type == "Money":
        amount = text_value(data.get("Amount"))
        if amount is not None and amount.lstrip("-").isdigit():
            return f"{int(amount)} 金币"
        multiplier = text_value(data.get("Multiplier"))
        if multiplier is not None and multiplier.lstrip("-").isdigit():
            return f"金币（按目标价值的 {int(multiplier)} 倍）"
        return None
    if reward_type == "Object":
        item_id = text_value(data.get("Item"))
        if item_id is None:
            return None
        target = by_id.get(f"object:{item_id}")
        name = (
            target.name_zh if target is not None and target.name_zh else item_id
        )
        amount = text_value(data.get("Amount"))
        if amount is not None and amount.lstrip("-").isdigit():
            return f"{name}×{int(amount)}"
        return name
    if reward_type == "Friendship":
        return "好感度"
    return None


GINGER_ISLAND_WEATHER_ZH = {
    "sunny": "晴天",
    "rain": "雨天",
    "wind": "大风天",
    "snow": "雪天",
    "storm": "暴风雨",
}


def _game_time_label(value: int) -> str:
    return f"{value // 100}:{value % 100:02d}"


def ginger_island_facts(
    entity: NormalizedEntity, attributes: dict[str, Any]
) -> list[Schema5FactSlot]:
    """姜岛事件：从官方事件脚本路径解析触发条件（天气/时间窗）。

    事件记录的 game_id 是官方事件脚本路径（如
    IslandSouth/6497428/e-6497423/f-Leo-1500/w-sunny/t-600-1800/Hl-leoMoved），
    其中 w-（天气）与 t-（时间窗）片段是玩家关心的触发条件；规范化的
    game_id 可能把分隔符折叠为空格（"w sunny"），因此按分隔符宽松匹配。
    """
    facts: list[Schema5FactSlot] = []
    source_id = entity.game_id or entity.internal_name or ""
    parts: list[str] = []
    weather = re.search(r"(?:^|[/\\\s])w[\s-]([A-Za-z]+)", source_id)
    if weather:
        raw = weather.group(1).casefold()
        parts.append(f"天气：{GINGER_ISLAND_WEATHER_ZH.get(raw, weather.group(1))}")
    window = re.search(r"(?:^|[/\\\s])t[\s-](\d+)[\s-](\d+)", source_id)
    if window:
        parts.append(
            f"时间：{_game_time_label(int(window.group(1)))}–{_game_time_label(int(window.group(2)))}"
        )
    if parts:
        facts.append(
            fixed_fact(
                entity, "ginger_trigger_condition", "text", text_value="，".join(parts)
            )
        )
    return facts


def typed_facts(
    entity: NormalizedEntity,
    *,
    by_id: dict[str, NormalizedEntity] | None = None,
    gift_index: dict[str, dict[str, list[str]]] | None = None,
    universal_gift: dict[str, set[str]] | None = None,
    drop_index: dict[str, dict[str, list[str]]] | None = None,
    shop_index: dict[str, list[str]] | None = None,
    fish_pond_index: dict[str, list[dict[str, object]]] | None = None,
    museum_index: dict[str, list[str]] | None = None,
    support: OfficialSupportData | None = None,
) -> list[Schema5FactSlot]:
    attributes = structured_attributes(entity)
    facts: list[Schema5FactSlot] = []
    if entity.entity_type == "quest":
        facts.extend(quest_facts(entity, attributes, by_id))
    if entity.entity_type == "achievement":
        facts.extend(achievement_facts(entity, attributes))
    if entity.entity_type == "bundle":
        facts.extend(bundle_facts(entity, attributes, by_id))
    if entity.entity_type == "special_order":
        facts.extend(special_order_facts(entity, attributes, by_id))
    if entity.entity_type == "tailoring_recipe":
        facts.extend(tailoring_facts(entity, attributes, by_id))
    if entity.entity_type == "drop":
        facts.extend(drop_facts(entity, attributes, by_id))
    if entity.entity_type in {"cooking_recipe", "crafting_recipe"}:
        facts.extend(
            recipe_source_facts(entity, attributes, support, by_id, shop_index)
        )
    if entity.entity_type == "cooking_recipe":
        facts.extend(recipe_effect_facts(entity, attributes, by_id))
    if entity.entity_type == "fish":
        facts.extend(fish_pond_facts(entity, fish_pond_index, by_id or {}))
    if entity.entity_type == "furniture":
        facts.extend(furniture_kind_facts(entity, attributes))
    if entity.entity_type == "crop":
        facts.extend(crop_harvest_quantity_facts(entity, attributes))
    if entity.entity_type == "object":
        facts.extend(food_effect_facts(entity, attributes))
        facts.extend(gift_liker_facts(entity, gift_index, universal_gift))
        facts.extend(drop_source_facts(entity, drop_index))
        facts.extend(museum_reward_facts(entity, museum_index))
    if entity.entity_type == "ginger_island":
        facts.extend(ginger_island_facts(entity, attributes))
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
            season_zh = SEASON_ZH.get(birthday[0].lower())
            if season_zh is not None:
                facts.append(
                    Schema5FactSlot(
                        id=f"fact:{entity.id}:birthday",
                        entity_id=entity.id,
                        slot_key="birthday",
                        status="fixed",
                        value_type="text",
                        text_value=f"{season_zh} {birthday[1]} 日",
                    )
                )
        residence = text_value(attributes.get("HomeRegion"))
        gender = text_value(attributes.get("Gender"))
        facts.extend(
            [
                fixed_fact(
                    entity,
                    "residence_region",
                    "text",
                    text_value=(
                        RESIDENCE_REGION_ZH.get(residence, "未注明") if residence else None
                    ),
                ),
                *(
                    [
                        fixed_fact(
                            entity,
                            "gender",
                            "text",
                            text_value=GENDER_ZH[gender],
                        )
                    ]
                    if gender in GENDER_ZH
                    else [
                        not_applicable_fact(entity, "gender")
                    ]
                ),
            ]
        )
    if entity.entity_type == "crop":
        facts.extend(
            [
                fixed_fact(
                    entity,
                    "seasons",
                    "text",
                    text_value=localized_seasons(attributes.get("Seasons")),
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
    if entity.entity_type == "tool":
        kind_zh = tool_kind_label(entity)
        if kind_zh is not None:
            facts.append(
                fixed_fact(entity, "tool_kind", "text", text_value=kind_zh)
            )
        level_zh = tool_level_label(entity)
        if level_zh is not None:
            facts.append(
                fixed_fact(entity, "tool_level", "text", text_value=level_zh)
            )
        upgrade_from = (
            attributes.get("UpgradeRequireToolId")
            or attributes.get("ConventionalUpgradeFrom")
        )
        if isinstance(upgrade_from, str) and upgrade_from:
            base = (
                upgrade_from.removeprefix("(T)")
                if upgrade_from.startswith("(T)")
                else upgrade_from
            )
            reference = f"tool:{base}"
            if (by_id or {}).get(reference) is not None:
                facts.append(
                    fixed_fact(entity, "upgrade_from_id", "text", text_value=reference)
                )
        if attributes.get("UpgradeMaterial"):
            # 官方 ClintUpgrade 商店与游戏规则：在铁匠铺升级，耗时 2 天。
            facts.append(
                fixed_fact(entity, "upgrade_location", "text", text_value="铁匠铺")
            )
            facts.append(
                fixed_fact(entity, "upgrade_time", "text", text_value="2 天")
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
            weapon_id = text_value(entity.game_id)
            if weapon_id in WEAPON_SCYTHE_IDS:
                type_zh = "镰刀"
            else:
                weapon_type = int_value(attributes.get("Type"))
                type_zh = WEAPON_TYPE_ZH.get(weapon_type) if weapon_type is not None else None
            if type_zh is not None:
                facts.append(
                    fixed_fact(
                        entity,
                        "weapon_type",
                        "text",
                        text_value=type_zh,
                    )
                )
            facts.append(
                fixed_fact(
                    entity,
                    "sell_price",
                    "integer",
                    integer_value=weapon_sell_price(entity, attributes),
                )
            )
            facts.extend(
                [
                    fixed_fact(
                        entity,
                        "weapon_speed",
                        "integer",
                        integer_value=int_value(attributes.get("Speed")),
                    ),
                    fixed_fact(
                        entity,
                        "weapon_precision",
                        "integer",
                        integer_value=int_value(attributes.get("Precision")),
                    ),
                    fixed_fact(
                        entity,
                        "weapon_defense",
                        "integer",
                        integer_value=int_value(attributes.get("Defense")),
                    ),
                ]
            )
            crit_chance = attributes.get("CritChance")
            if isinstance(crit_chance, int | float) and not isinstance(crit_chance, bool):
                facts.append(
                    fixed_fact(
                        entity,
                        "weapon_crit_chance",
                        "text",
                        text_value=percent_label(crit_chance * 100),
                    )
                )
            crit_multiplier = attributes.get("CritMultiplier")
            if isinstance(crit_multiplier, int | float) and not isinstance(
                crit_multiplier, bool
            ):
                facts.append(
                    fixed_fact(
                        entity,
                        "weapon_crit_multiplier",
                        "text",
                        text_value=f"{crit_multiplier:g}×",
                    )
                )
    if entity.entity_type == "monster":
        facts.extend(
            [
                fixed_fact(
                    entity,
                    "health",
                    "integer",
                    integer_value=int_value(attributes.get("monsterHealth")),
                ),
                fixed_fact(
                    entity,
                    "damage",
                    "integer",
                    integer_value=int_value(attributes.get("monsterDamage")),
                ),
                fixed_fact(
                    entity,
                    "monster_xp",
                    "integer",
                    integer_value=int_value(attributes.get("monsterXp")),
                ),
                fixed_fact(
                    entity,
                    "monster_resilience",
                    "integer",
                    integer_value=int_value(attributes.get("monsterResilience")),
                ),
            ]
        )
    if entity.entity_type == "footwear":
        facts.extend(
            [
                fixed_fact(
                    entity,
                    "defense",
                    "integer",
                    integer_value=int_value(attributes.get("footwearDefense")),
                ),
                fixed_fact(
                    entity,
                    "immunity",
                    "integer",
                    integer_value=int_value(attributes.get("footwearImmunity")),
                ),
            ]
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
                        text_value=(
                            FISH_BEHAVIOR_ZH.get(behavior)
                            if (behavior := text_value(attributes.get("Behavior"))) is not None
                            else None
                        ),
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
                        text_value=localized_fishing_time(attributes.get("FishingTime")),
                    ),
                    fixed_fact(
                        entity,
                        "seasons",
                        "text",
                        text_value=localized_seasons(attributes.get("Seasons")),
                    ),
                    fixed_fact(
                        entity,
                        "weather",
                        "text",
                        text_value=(
                            FISH_WEATHER_ZH.get(weather)
                            if (weather := text_value(attributes.get("Weather"))) is not None
                            else None
                        ),
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
