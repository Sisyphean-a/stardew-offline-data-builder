from __future__ import annotations

from builder.models import RawEntity
from builder.pipeline.normalize import normalize_entities
from builder.pipeline.publish import filter_publishable_entities


def raw(
    entity_type: str,
    source_id: str,
    *,
    name: str | None = None,
    locale: str | None = "en",
    attributes: dict[str, object] | None = None,
    source_file: str | None = None,
) -> RawEntity:
    return RawEntity(
        source="official",
        entity_type=entity_type,
        source_id=source_id,
        internal_name=source_id,
        name=name,
        description=None,
        locale=locale,
        attributes=attributes or {},
        source_file=source_file or f"Data/{entity_type}.json",
    )


def test_publish_filter_keeps_contextual_records_but_removes_only_explicit_false() -> None:
    entities = normalize_entities(
        [
            raw(
                "villager",
                "Abigail",
                name="阿比盖尔",
                locale="zh-CN",
                attributes={"CanSocialize": False},
            ),
            raw(
                "villager",
                "Leo",
                name="里奥",
                locale="zh-CN",
                attributes={"CanSocialize": True},
            ),
            raw("villager", "Missing", name="缺失值", attributes={}),
            raw("villager", "Null", name="空值", attributes={"CanSocialize": None}),
            raw("villager", "TextFalse", name="文本假值", attributes={"CanSocialize": "false"}),
            raw("villager", "Invalid", name="非法值", attributes={"CanSocialize": "0"}),
            raw("villager", "Zero", name="数字零", attributes={"CanSocialize": 0}),
            raw("npc_schedule", "Abigail:Wed_6", name="Abigail:Wed_6"),
            raw("villager_gift", "Abigail", name="Abigail"),
        ],
        aliases={"villager:Abigail": ["阿比"]},
        categories={},
    )
    by_id = {entity.id: entity for entity in entities}

    assert by_id["villager:Abigail"].extra_json["CanSocialize"] is False
    assert by_id["villager:Abigail"].aliases == ["阿比"]
    assert "阿比盖尔" in by_id["npc_schedule:Abigail:Wed_6"].name_zh
    assert by_id["villager_gift:Abigail"].name_zh.startswith("阿比盖尔")

    published = filter_publishable_entities(entities)
    published_ids = {entity.id for entity in published}

    assert "villager:Abigail" not in published_ids
    assert "villager:TextFalse" not in published_ids
    assert {
        "villager:Leo",
        "villager:Missing",
        "villager:Null",
        "villager:Invalid",
        "villager:Zero",
        "npc_schedule:Abigail:Wed_6",
        "villager_gift:Abigail",
    } <= published_ids


def test_publish_filter_removes_shops_without_user_visible_options() -> None:
    entities = normalize_entities(
        [
            raw(
                "shop",
                "SingingStone",
                attributes={"ItemId": "(BC)94"},
                source_file="Data/LostItemsShop.json",
            ),
            raw(
                "shop",
                "EmptyShop",
                attributes={"Items": [{"Id": "empty"}]},
                source_file="Data/Shops.json",
            ),
            raw("weapon", "1", name="测试武器"),
            raw("object", "MixedFlowerSeeds", name="混合花卉种子"),
            raw("furniture", "SamsSkateboard", name="山姆的滑板"),
            raw(
                "shop",
                "AdventureShop",
                attributes={"Items": [{"Id": "sword", "ItemId": "(W)1"}]},
                source_file="Data/Shops.json",
            ),
            raw(
                "shop",
                "WizardFurnitureCatalogue",
                attributes={"Items": [{"Id": "all", "ItemId": "ALL_ITEMS (F)"}]},
                source_file="Data/Shops.json",
            ),
            raw(
                "shop",
                "NamedFurnitureShop",
                attributes={"Items": [{"Id": "skateboard", "ItemId": "SamsSkateboard"}]},
                source_file="Data/Shops.json",
            ),
        ],
        aliases={},
        categories={},
    )

    published_ids = {entity.id for entity in filter_publishable_entities(entities)}

    assert "shop:SingingStone" not in published_ids
    assert "shop:EmptyShop" not in published_ids
    assert "shop:AdventureShop" in published_ids
    assert "shop:WizardFurnitureCatalogue" not in published_ids
    assert "shop:NamedFurnitureShop" in published_ids


def test_schedule_titles_follow_context_rules_and_hide_technical_english() -> None:
    entities = normalize_entities(
        [
            raw("villager", "Abigail", name="阿比盖尔", locale="zh-CN"),
            raw("villager", "Leo", name="里奥", locale="zh-CN"),
            raw("npc_schedule", "Abigail:Wed_6", name="Abigail:Wed_6"),
            raw("npc_schedule", "Abigail:fall_Mon", name="Abigail:fall_Mon"),
            raw(
                "npc_schedule",
                "Abigail:DesertFestival_1",
                name="Abigail:DesertFestival_1",
            ),
            raw("npc_schedule", "Abigail:marriage_Fri", name="Abigail:marriage_Fri"),
            raw("npc_schedule", "Abigail:16", name="Abigail:16"),
            raw("npc_schedule", "Abigail:GreenRain_2", name="Abigail:GreenRain_2"),
            raw("npc_schedule", "Abigail:unknown_4", name="Abigail:unknown_4"),
            raw("npc_schedule", "LeoMainland:23", name="LeoMainland:23"),
            raw("npc_schedule", "Leo:Sun", name="Leo:Sun"),
            raw("npc_schedule", "LeoMainland:Sun", name="LeoMainland:Sun"),
            raw("npc_schedule", "Alex:Sun_normal", name="Alex:Sun_normal"),
            raw(
                "npc_schedule",
                "Clint:CommunityCenter_Replacement",
                name="Clint:CommunityCenter_Replacement",
            ),
            raw("npc_schedule", "Elliott:SquidFest", name="Elliott:SquidFest"),
            raw("npc_schedule", "Harvey:marriageJob", name="Harvey:marriageJob"),
            raw("npc_schedule", "Lewis:default", name="Lewis:default"),
            raw("npc_schedule", "Jodi:JojaMart_Replacement", name="Jodi:JojaMart_Replacement"),
            raw("npc_schedule", "Pam:bus", name="Pam:bus"),
            raw("npc_schedule", "Willy:TroutDerby", name="Willy:TroutDerby"),
            raw("npc_schedule", "Leah:summer_noBridge", name="Leah:summer_noBridge"),
            raw("npc_schedule", "template:24", name="template:24"),
            raw("npc_schedule", "template:Wed_6", name="template:Wed_6"),
        ],
        aliases={},
        categories={},
    )
    by_id = {entity.id: entity for entity in entities}

    assert by_id["npc_schedule:Abigail:Wed_6"].name_zh == "阿比盖尔的周三变体6日程"
    assert by_id["npc_schedule:Abigail:fall_Mon"].name_zh == "阿比盖尔的秋季·周一日程"
    assert (
        by_id["npc_schedule:Abigail:DesertFestival_1"].name_zh
        == "阿比盖尔的沙漠节变体1日程"
    )
    assert by_id["npc_schedule:Abigail:marriage_Fri"].name_zh == "阿比盖尔的婚后·周五日程"
    assert by_id["npc_schedule:Abigail:16"].name_zh == "阿比盖尔的第16天日程"
    assert by_id["npc_schedule:Abigail:GreenRain_2"].name_zh == "阿比盖尔的绿雨天变体2日程"
    assert "条件/变体：unknown（变体4）" in by_id["npc_schedule:Abigail:unknown_4"].name_zh
    assert by_id["npc_schedule:LeoMainland:23"].name_zh == "里奥的大陆版本·第23天日程"
    assert "大陆版本" in by_id["npc_schedule:LeoMainland:Sun"].name_zh
    assert by_id["npc_schedule:Leo:Sun"].name_zh != by_id["npc_schedule:LeoMainland:Sun"].name_zh
    assert "普通" in by_id["npc_schedule:Alex:Sun_normal"].name_zh
    assert "社区中心·替代" in by_id["npc_schedule:Clint:CommunityCenter_Replacement"].name_zh
    assert "鱿鱼节" in by_id["npc_schedule:Elliott:SquidFest"].name_zh
    assert "婚后工作" in by_id["npc_schedule:Harvey:marriageJob"].name_zh
    assert "默认" in by_id["npc_schedule:Lewis:default"].name_zh
    assert "乔家超市·替代" in by_id["npc_schedule:Jodi:JojaMart_Replacement"].name_zh
    assert "巴士" in by_id["npc_schedule:Pam:bus"].name_zh
    assert "鳟鱼大赛" in by_id["npc_schedule:Willy:TroutDerby"].name_zh
    assert "夏季·无桥" in by_id["npc_schedule:Leah:summer_noBridge"].name_zh
    assert by_id["npc_schedule:template:24"].name_zh == "通用模板·第24天日程"
    assert by_id["npc_schedule:template:Wed_6"].name_zh == "通用模板·周三变体6日程"
    for entity in by_id.values():
        if entity.entity_type == "npc_schedule":
            assert entity.name_en is None
            assert "_" not in entity.name_zh


def test_gift_titles_cover_universal_preferences_and_avatar_metadata() -> None:
    entities = normalize_entities(
        [
            raw(
                "villager",
                "Abigail",
                name="阿比盖尔",
                locale="zh-CN",
                attributes={
                    "imageSource": "Portraits/Abigail.png",
                    "imageRect": [0, 0, 32, 64],
                    "imageFallbackRect": [0, 0, 16, 32],
                    "imageMode": "portrait",
                },
                source_file="Data/Characters.json",
            ),
            raw("villager_gift", "Abigail", name="Abigail"),
            raw("villager_gift", "Universal_Love", name="Universal_Love"),
        ],
        aliases={},
        categories={},
    )
    by_id = {entity.id: entity for entity in entities}

    assert by_id["villager_gift:Abigail"].name_zh == "阿比盖尔的礼物偏好"
    assert by_id["villager_gift:Universal_Love"].name_zh == "通用礼物偏好：最爱"
    assert by_id["villager_gift:Universal_Love"].name_en is None
    gift_extra = by_id["villager_gift:Abigail"].extra_json
    assert gift_extra["imageSource"] == "Portraits/Abigail.png"
    assert gift_extra["imageRect"] == [0, 0, 32, 64]
    assert gift_extra["imageFallbackRect"] == [0, 0, 16, 32]
    assert gift_extra["imageMode"] == "portrait"
    assert gift_extra["imageRequired"] is False
    assert gift_extra["_provenance"] == {
        "official": ["Data/Characters.json", "Data/villager_gift.json"]
    }


def test_drop_titles_include_monster_item_and_record_marker() -> None:
    entities = normalize_entities(
        [
            raw("monster", "Bat", name="蝙蝠"),
            raw("object", "999", name="测试物品"),
            raw(
                "drop",
                "Bat:0",
                attributes={"monsterId": "Bat", "itemId": "999"},
            ),
            raw(
                "drop",
                "Bat:1",
                attributes={"monsterId": "Bat", "itemId": "999"},
            ),
        ],
        aliases={},
        categories={},
    )
    drops = [entity for entity in entities if entity.entity_type == "drop"]

    assert len({drop.name_zh for drop in drops}) == 2
    for drop in drops:
        assert "蝙蝠" in drop.name_zh
        assert "测试物品" in drop.name_zh
        assert "记录" in drop.name_zh
        assert drop.name_en is None


def test_known_shop_tailoring_and_ginger_titles_are_readable() -> None:
    entities = normalize_entities(
        [
            raw("object", "999", name="测试产物"),
            raw("shop", "SeedShop"),
            raw(
                "tailoring_recipe",
                "recipe-1",
                attributes={"CraftedItemId": "999"},
            ),
            raw("ginger_island", "IslandWest:event/script/value"),
        ],
        aliases={},
        categories={},
    )
    by_type = {entity.entity_type: entity for entity in entities}

    assert by_type["shop"].name_zh == "皮埃尔商店"
    assert by_type["tailoring_recipe"].name_zh == "裁缝配方：测试产物"
    assert by_type["ginger_island"].name_zh == "姜岛事件：姜岛西部·事件/条件：event"
    for entity_type in ("shop", "tailoring_recipe", "ginger_island"):
        entity = by_type[entity_type]
        assert entity.name_en is None
        assert "script" not in entity.name_zh
        assert "未命名" not in entity.name_zh


def test_shop_titles_use_chinese_labels_and_lost_item_names() -> None:
    entities = normalize_entities(
        [
            raw("villager", "Abigail", name="阿比盖尔", locale="zh-CN"),
            raw("furniture", "1306", name="利亚的雕像", locale="zh-CN"),
            raw("shop", "AdventureShop"),
            raw("shop", "DesertFestival_Abigail"),
            raw(
                "shop",
                "LeahsSculpture",
                attributes={"ItemId": "(F)1306"},
                source_file="Data/LostItemsShop.json",
            ),
            raw(
                "shop",
                "EmilysMagicHat",
                attributes={"ItemId": "(H)41"},
                source_file="Data/LostItemsShop.json",
            ),
        ],
        aliases={},
        categories={},
    )
    by_id = {entity.id: entity for entity in entities}

    assert by_id["shop:AdventureShop"].name_zh == "冒险家公会商店"
    assert by_id["shop:DesertFestival_Abigail"].name_zh == "沙漠节：阿比盖尔"
    assert by_id["shop:LeahsSculpture"].name_zh == "利亚的雕像"
    assert by_id["shop:EmilysMagicHat"].name_zh == "艾米丽的魔法帽"
    for entity in by_id.values():
        if entity.entity_type == "shop":
            assert entity.name_en is None
            assert entity.name_zh != ""


def test_unresolved_tailoring_outputs_use_source_variants() -> None:
    entities = normalize_entities(
        [
            raw(
                "tailoring_recipe",
                "BasicPullover_FromFiber",
                attributes={"CraftedItemId": "(S)1176"},
            ),
            raw(
                "tailoring_recipe",
                "BasicPullover_FromWood",
                attributes={"CraftedItemId": "(S)1176"},
            ),
        ],
        aliases={},
        categories={},
    )
    recipes = [entity for entity in entities if entity.entity_type == "tailoring_recipe"]

    assert len({recipe.name_zh for recipe in recipes}) == 2
    assert "裁缝配方：Basic Pullover（材料：Fiber）" in {
        recipe.name_zh for recipe in recipes
    }
    assert "裁缝配方：Basic Pullover（材料：Wood）" in {
        recipe.name_zh for recipe in recipes
    }
    assert all(recipe.name_en is None for recipe in recipes)
    assert all("CraftedItem" not in recipe.name_zh for recipe in recipes)
    assert all("(S)1176" not in recipe.name_zh for recipe in recipes)


def test_unresolved_tailoring_uses_number_only_without_source_subject() -> None:
    entities = normalize_entities(
        [
            raw(
                "tailoring_recipe",
                "(S)1176",
                attributes={"CraftedItemId": "(S)1176"},
            )
        ],
        aliases={},
        categories={},
    )

    assert entities[0].name_zh == "裁缝配方：编号：1176"


def test_ginger_island_known_event_markers_are_localized() -> None:
    entities = normalize_entities(
        [
            raw("ginger_island", "IslandHut:1039573/N-10/Hl-addedParrotBoy"),
            raw("ginger_island", "IslandNorth:6497421/Hl-leoMoved"),
        ],
        aliases={},
        categories={},
    )
    titles = [entity.name_zh for entity in entities]

    assert any("鹦鹉男孩加入" in title for title in titles)
    assert any("里奥搬迁" in title for title in titles)
    assert all("addedParrotBoy" not in title and "leoMoved" not in title for title in titles)


def test_drop_without_links_keeps_explicit_fallback() -> None:
    entity = next(
        item
        for item in normalize_entities(
            [raw("drop", "Monster:0")], aliases={}, categories={}
        )
        if item.entity_type == "drop"
    )

    assert "怪物（未知）" in entity.name_zh
    assert "物品（未知）" in entity.name_zh
    assert "记录0" in entity.name_zh
    assert entity.name_en is None
