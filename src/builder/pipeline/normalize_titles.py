from __future__ import annotations

import re

from builder.models import NormalizedEntity
from builder.pipeline.normalize_images import copy_avatar_metadata, inherit_harvest_item_image
from builder.pipeline.normalize_schedule import (
    display_villager_name,
    referenced_villager,
    resolve_schedule_title,
)
from builder.pipeline.normalize_support import (
    displayable_entity_name,
    drop_record_id,
    humanize_identifier,
    item_key_value,
    reference_key,
    technical_name,
)
from builder.pipeline.provenance import merge_provenance


def apply_contextual_display_data(
    entity: NormalizedEntity,
    villagers: dict[str, NormalizedEntity],
    items: dict[str, NormalizedEntity],
    monsters: dict[str, NormalizedEntity],
) -> NormalizedEntity:
    if entity.entity_type == "crop":
        return inherit_harvest_item_image(entity, items)
    if entity.entity_type == "drop":
        return resolve_drop_title(entity, items, monsters)
    if entity.entity_type == "npc_schedule":
        return resolve_schedule_title(entity, villagers)
    if entity.entity_type == "villager_gift":
        return resolve_gift_title(entity, villagers)
    title_builders = {
        "shop": lambda: shop_title(entity, items, villagers),
        "tailoring_recipe": lambda: tailoring_title(entity, items),
        "ginger_island": lambda: ginger_island_title(entity),
    }
    builder = title_builders.get(entity.entity_type)
    if builder is None:
        return entity
    return entity.model_copy(update={"name_zh": builder(), "name_en": None})


def resolve_gift_title(
    entity: NormalizedEntity, villagers: dict[str, NormalizedEntity]
) -> NormalizedEntity:
    key = (entity.game_id or entity.internal_name or "").strip()
    if key.casefold().startswith("universal_"):
        preference = {
            "dislike": "不喜欢",
            "hate": "厌恶",
            "like": "喜欢",
            "love": "最爱",
            "neutral": "一般",
        }.get(key.rsplit("_", maxsplit=1)[-1].casefold())
        title = f"通用礼物偏好：{preference or '未分类'}"
    else:
        npc = referenced_villager(entity, villagers)
        title = f"{display_villager_name(npc, entity)}的礼物偏好"
    npc = referenced_villager(entity, villagers)
    extra_json = (
        copy_avatar_metadata(entity.extra_json, npc.extra_json)
        if npc
        else merge_provenance(entity.extra_json)
    )
    return entity.model_copy(
        update={"name_zh": title, "name_en": None, "extra_json": extra_json}
    )


def resolve_drop_title(
    entity: NormalizedEntity,
    items: dict[str, NormalizedEntity],
    monsters: dict[str, NormalizedEntity],
) -> NormalizedEntity:
    item_id = entity.extra_json.get("itemId")
    monster_id = entity.extra_json.get("monsterId")
    item = items.get(item_key_value(item_id))
    monster = monsters.get(reference_key(monster_id))
    item_name = displayable_entity_name(item, item_id, "物品")
    monster_name = displayable_entity_name(monster, monster_id, "怪物")
    title = f"{monster_name}掉落：{item_name}（记录{drop_record_id(entity)}）"
    return entity.model_copy(update={"name_zh": title, "name_en": None})


SHOP_TITLES = {
    "AdventureGuildRecovery": "冒险家公会恢复",
    "AdventureShop": "冒险家公会商店",
    "AnimalShop": "玛妮的牧场",
    "Blacksmith": "铁匠铺",
    "Bookseller": "书摊老板",
    "BooksellerTrade": "书摊交易",
    "BoxOffice": "电影院售票处",
    "Carpenter": "木匠铺",
    "Casino": "赌场",
    "Catalogue": "目录",
    "ClintUpgrade": "克林特的工具升级",
    "Concessions": "电影院小卖部",
    "DesertTrade": "沙漠节交易",
    "Dwarf": "矮人商店",
    "FishShop": "威利的鱼店",
    "Furniture Catalogue": "家具目录",
    "HatMouse": "帽子老鼠商店",
    "Hospital": "哈维的诊所",
    "IceCreamStand": "冰淇淋摊",
    "IslandTrade": "姜岛交易",
    "Joja": "Joja 超市",
    "JojaFurnitureCatalogue": "Joja 家具目录",
    "JunimoFurnitureCatalogue": "祝尼魔目录",
    "LostItems": "失物商店",
    "PetAdoption": "宠物领养",
    "QiGemShop": "齐先生的宝石商店",
    "Raccoon": "浣熊商店",
    "ResortBar": "度假村酒吧",
    "RetroFurnitureCatalogue": "复古目录",
    "Saloon": "酒吧",
    "Sandy": "桑迪的绿洲商店",
    "SeedShop": "皮埃尔商店",
    "ShadowShop": "暗影商店",
    "TrashFurnitureCatalogue": "垃圾目录",
    "Traveler": "旅行货车",
    "VolcanoShop": "火山商店",
    "WizardFurnitureCatalogue": "法师目录",
}

FESTIVAL_SHOP_TITLES = {
    "Festival_DanceOfTheMoonlightJellies_Pierre": "月光水母节：皮埃尔",
    "Festival_EggFestival_Pierre": "复活节：皮埃尔",
    "Festival_FeastOfTheWinterStar_Pierre": "冬日星盛宴：皮埃尔",
    "Festival_FestivalOfIce_TravelingMerchant": "冰雪节：旅行商人",
    "Festival_FlowerDance_Pierre": "花舞节：皮埃尔",
    "Festival_Luau_Pierre": "夏威夷宴会：皮埃尔",
    "Festival_NightMarket_DecorationBoat": "夜市：装饰船",
    "Festival_NightMarket_MagicBoat_Day1": "夜市：魔法船（第1天）",
    "Festival_NightMarket_MagicBoat_Day2": "夜市：魔法船（第2天）",
    "Festival_NightMarket_MagicBoat_Day3": "夜市：魔法船（第3天）",
    "Festival_SpiritsEve_Pierre": "万灵节：皮埃尔",
    "Festival_StardewValleyFair_StarTokens": "星露谷展览会：星币兑换",
}

VILLAGER_DISPLAY_NAMES = {
    "abigail": "阿比盖尔",
    "alex": "亚历克斯",
    "caroline": "卡洛琳",
    "clint": "克林特",
    "demetrius": "德米特里厄斯",
    "elliott": "艾利欧特",
    "emily": "艾米丽",
    "evelyn": "伊芙琳",
    "george": "乔治",
    "gus": "格斯",
    "haley": "海莉",
    "harvey": "哈维",
    "jas": "贾丝",
    "jodi": "乔迪",
    "kent": "肯特",
    "leah": "莉亚",
    "leo": "里奥",
    "marnie": "玛妮",
    "maru": "玛鲁",
    "pam": "潘姆",
    "penny": "潘妮",
    "pierre": "皮埃尔",
    "robin": "罗宾",
    "sam": "山姆",
    "sebastian": "塞巴斯蒂安",
    "shane": "谢恩",
    "vincent": "文森特",
}

LOST_ITEM_TITLES = {
    "(h)41": "艾米丽的魔法帽",
    "(h)75": "金色头盔",
    "(h)92": "???",
    "(h)gilshat": "吉尔的帽子",
    "(s)1127": "艾米丽的魔法衬衫",
}

# 官方 zh-CN 字符串未翻译（游戏内也显示英文）时，按社区通用译名补齐显示名。
# 键为 (entity_type, source_id)；仅当官方中文名不含中文时生效，官方补翻译后自动让位。
OFFICIAL_ZH_GAP_NAMES: dict[tuple[str, str], str] = {
    ("monster", "Iridium Golem"): "铱石魔",
    ("monster", "Truffle Crab"): "松露蟹",
    ("object", "742"): "海莉丢失的手镯",
    ("object", "DriedFruit"): "果干",
    ("object", "DriedMushrooms"): "干蘑菇",
    ("object", "SmokedFish"): "熏鱼",
    ("furniture", "CCFishTank"): "社区中心鱼缸",
    ("furniture", "J"): "Joja 标志画",
    ("furniture", "UFO"): "UFO 摆件",
    ("big_craftable", "221"): "物品展示台",
    ("big_craftable", "155"): "大型可制作物（未命名，编号 155）",
}


def shop_title(
    entity: NormalizedEntity,
    items: dict[str, NormalizedEntity] | None = None,
    villagers: dict[str, NormalizedEntity] | None = None,
) -> str:
    identifier = (entity.game_id or entity.internal_name or "").strip()
    item_index = items or {}
    villager_index = villagers or {}
    if entity.source_file.replace("\\", "/").endswith("/LostItemsShop.json"):
        return lost_item_title(entity, item_index)
    if identifier in SHOP_TITLES:
        return SHOP_TITLES[identifier]
    if identifier in FESTIVAL_SHOP_TITLES:
        return FESTIVAL_SHOP_TITLES[identifier]
    if identifier == "DesertFestival_EggShop":
        return "沙漠节：蛋摊"
    if identifier.startswith("DesertFestival_"):
        owner = identifier.removeprefix("DesertFestival_")
        owner_key = reference_key(owner)
        owner_name = displayable_entity_name(
            villager_index.get(owner_key),
            VILLAGER_DISPLAY_NAMES.get(owner_key, "村民"),
            "村民",
        )
        return f"沙漠节：{owner_name}"
    return "特殊商店"


def lost_item_title(entity: NormalizedEntity, items: dict[str, NormalizedEntity]) -> str:
    item_id = str(entity.extra_json.get("ItemId") or "").strip()
    known_title = LOST_ITEM_TITLES.get(item_id.casefold())
    if known_title:
        return known_title
    item = items.get(item_reference_key(item_id)) or items.get(item_key_value(item_id))
    return displayable_entity_name(item, item_id, "失物")


def item_reference_key(value: str) -> str:
    prefix = value[: value.find(")") + 1].casefold() if ")" in value else ""
    entity_type = {
        "(o)": "object",
        "(bc)": "big_craftable",
        "(b)": "footwear",
        "(f)": "furniture",
        "(t)": "tool",
        "(w)": "weapon",
    }.get(prefix)
    return f"{entity_type}:{item_key_value(value)}" if entity_type else ""


def tailoring_title(
    entity: NormalizedEntity, items: dict[str, NormalizedEntity]
) -> str:
    output = entity.extra_json.get("CraftedItemId")
    outputs = entity.extra_json.get("CraftedItemIds")
    if output is None and isinstance(outputs, list) and outputs:
        output = outputs[0]
    output_text = str(output or "").strip()
    item = (
        items.get(item_key_value(output))
        if output_text[:3].casefold() not in {"(h)", "(p)", "(s)"}
        else None
    )
    if item is not None:
        output_name = displayable_entity_name(item, output, "产物")
    else:
        output_name = tailoring_source_title(entity)
        if not output_name:
            value = output_text or str(entity.game_id or "").strip()
            output_name = f"编号：{tailoring_fallback_identifier(value)}"
    return f"裁缝配方：{output_name}"


def tailoring_source_title(entity: NormalizedEntity) -> str:
    source_key = (entity.game_id or entity.internal_name or "").strip()
    if not source_key or "/" in source_key or "\\" in source_key:
        return ""
    match = re.fullmatch(
        r"(?P<subject>[A-Za-z][A-Za-z0-9]*?)[_-]From(?P<variant>[A-Za-z0-9][A-Za-z0-9_()\-]*)",
        source_key,
    )
    if match:
        subject = humanize_identifier(match.group("subject"))
        variant = humanize_identifier(match.group("variant"))
        return f"{subject}（材料：{variant}）" if subject and variant else subject
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z][A-Za-z0-9_()\-]*", source_key):
        subject, variant = source_key.split("_", maxsplit=1)
        subject_name = humanize_identifier(subject)
        variant_name = humanize_identifier(variant)
        if subject_name and variant_name:
            return f"{subject_name}（材料：{variant_name}）"
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", source_key):
        return humanize_identifier(source_key)
    return ""


def tailoring_fallback_identifier(value: str) -> str:
    qualified = re.fullmatch(r"\([HPS]\)(\d+)", value.strip(), re.IGNORECASE)
    return qualified.group(1) if qualified else humanize_identifier(value)


def ginger_island_title(entity: NormalizedEntity) -> str:
    source_id = entity.game_id or entity.internal_name or ""
    map_id, _, event_id = source_id.partition(":")
    map_name = {
        "islandhut": "姜岛小屋",
        "islandnorth": "姜岛北部",
        "islandsouth": "姜岛南部",
        "islandwest": "姜岛西部",
    }.get(map_id.casefold(), humanize_identifier(map_id))
    summary = "·".join(part for part in (map_name, ginger_event_name(event_id)) if part)
    return f"姜岛事件：{summary or '未命名（编号未知）'}"


def ginger_event_name(event_id: str) -> str:
    known_events = {
        "addedparrotboy": "鹦鹉男孩加入",
        "islanddepart": "离开姜岛",
        "leomoved": "里奥搬迁",
        "playerkilled": "玩家倒下",
    }
    tokens = [token for token in re.split(r"[/\\\s]+", event_id) if token]
    for token in reversed(tokens):
        marker = token.removeprefix("Hl-").casefold()
        if marker in known_events:
            return known_events[marker]
    friendly = humanize_identifier(tokens[0]) if tokens else ""
    return f"事件/条件：{friendly}" if friendly else "事件/条件：未知"


def fallback_name(primary: object, name: str | None) -> str:
    entity_type = primary.entity_type
    source_id = primary.source_id
    gap_name = OFFICIAL_ZH_GAP_NAMES.get((entity_type, str(source_id or "").strip()))
    if gap_name is not None and name and not re.search(r"[\u4e00-\u9fff]", name):
        return gap_name
    if entity_type in {"npc_schedule", "villager_gift"}:
        return name or "未命名"
    if entity_type in {"ginger_island", "shop", "tailoring_recipe"}:
        label = {
            "ginger_island": "姜岛数据",
            "shop": "商店",
            "tailoring_recipe": "裁缝规则",
        }[entity_type]
        return labelled_identifier(label, source_id)
    if entity_type == "drop":
        item_id = primary.attributes.get("itemId")
        if (
            name
            and name.strip()
            and not technical_name(name)
            and name.strip() != str(item_id or source_id).strip()
        ):
            return name.strip()
        return labelled_identifier("掉落物", item_id or source_id)
    if name and name.strip() and not technical_name(name):
        return name.strip()
    return labelled_identifier(entity_type.replace("_", " "), source_id)


def labelled_identifier(label: str, value: object) -> str:
    identifier = humanize_identifier(str(value).strip()) if value is not None else ""
    return f"{label}（未命名，编号：{identifier or '未知'}）"
