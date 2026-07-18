from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tests.real_official_entities import add_primary_objects, object_data


def create_real_layout(tmp_path: Path) -> Path:
    game_dir = tmp_path / "真实游戏"
    unpacked_dir = game_dir / "Content (unpacked)"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    add_primary_objects(unpacked_dir, write_json)
    write_json(
        unpacked_dir / "Data" / "Crops.json",
        {
            "472": {
                "Seasons": ["Spring"],
                "DaysInPhase": [1, 1, 1, 1],
                "RegrowDays": -1,
                "NeedsWatering": True,
                "IsPaddyCrop": False,
                "IsRaised": False,
                "HarvestItemId": "24",
                "HarvestMinStack": 1,
                "HarvestMaxStack": 1,
                "Texture": "TileSheets\\crops",
                "SpriteIndex": 0,
            }
        },
    )
    write_json(
        unpacked_dir / "Data" / "Fish.json",
        {"128": "Pufferfish/80/floater/1/36/1200 1600/summer/sunny"},
    )
    write_json(
        unpacked_dir / "Data" / "Monsters.json",
        {"Green Slime": monster_record("Green Slime")},
    )
    write_json(
        unpacked_dir / "Data" / "Monsters.zh-CN.json",
        {"Green Slime": monster_record("绿色史莱姆")},
    )
    write_json(
        unpacked_dir / "Data" / "Characters.json",
        {"Abigail": {"DisplayName": "[LocalizedText Strings\\NPCNames:Abigail]"}},
    )
    add_official_support_data(unpacked_dir)
    add_localization_strings(unpacked_dir)
    write_image(unpacked_dir / "Maps" / "springobjects.png", (32, 16))
    write_image(unpacked_dir / "TileSheets" / "crops.png", (16, 16))
    write_image(unpacked_dir / "Portraits" / "Abigail.png", (32, 64))
    return game_dir


def add_localization_strings(unpacked_dir: Path) -> None:
    write_json(
        unpacked_dir / "Strings" / "Objects.json",
        {
            "Parsnip_Name": "Parsnip",
            "Parsnip_Description": "A spring tuber.",
            "Pufferfish_Name": "Pufferfish",
            "Pufferfish_Description": "Inflates when threatened.",
            "ParsnipSeeds_Name": "Parsnip Seeds",
            "ParsnipSeeds_Description": "Plant these in spring.",
            "Amethyst_Name": "Amethyst",
            "Amethyst_Description": "A purple crystal.",
            "GlowRing_Name": "Glow Ring",
            "GlowRing_Description": "Provides light.",
        },
    )
    write_json(
        unpacked_dir / "Strings" / "Objects.zh-CN.json",
        {
            "Parsnip_Name": "防风草",
            "Parsnip_Description": "一种春季块茎。",
            "Pufferfish_Name": "河豚",
            "Pufferfish_Description": "受到威胁时会膨胀。",
            "ParsnipSeeds_Name": "防风草种子",
            "ParsnipSeeds_Description": "春季播种。",
            "Amethyst_Name": "紫水晶",
            "Amethyst_Description": "一种紫色水晶。",
            "GlowRing_Name": "光辉戒指",
            "GlowRing_Description": "提供光亮。",
        },
    )
    write_json(unpacked_dir / "Strings" / "NPCNames.json", {"Abigail": "Abigail"})
    write_json(unpacked_dir / "Strings" / "NPCNames.zh-CN.json", {"Abigail": "阿比盖尔"})


def add_official_support_data(unpacked_dir: Path) -> None:
    add_shop_data(unpacked_dir)
    add_fishing_support_data(unpacked_dir)
    add_machine_data(unpacked_dir)


def add_shop_data(unpacked_dir: Path) -> None:
    write_json(
        unpacked_dir / "Data" / "Shops.json",
        {
            "SeedShop": {
                "Items": [
                    {
                        "ItemId": "(O)472",
                        "Price": 20,
                        "Condition": "SEASON spring",
                        "IsRecipe": False,
                    }
                ]
            }
        },
    )


def add_fishing_support_data(unpacked_dir: Path) -> None:
    write_json(
        unpacked_dir / "Data" / "Locations.json",
        {
            "Beach": {
                "Fish": [
                    {
                        "ItemId": "(O)128",
                        "Chance": 0.2,
                        "Season": "Summer",
                        "MinFishingLevel": 0,
                    }
                ]
            }
        },
    )
    write_json(
        unpacked_dir / "Data" / "FishPondData.json",
        [
            {
                "Id": "Pufferfish",
                "RequiredTags": ["item_pufferfish"],
                "MaxPopulation": 10,
                "ProducedItems": [
                    {
                        "ItemId": "(O)812",
                        "RequiredPopulation": 1,
                        "Chance": 1.0,
                    }
                ],
            }
        ],
    )


def add_machine_data(unpacked_dir: Path) -> None:
    write_json(
        unpacked_dir / "Data" / "Machines.json",
        {
            "(BC)FishSmoker": {
                "OutputRules": [
                    {
                        "Id": "SmokeFish",
                        "Triggers": [
                            {
                                "Id": "Pufferfish",
                                "RequiredTags": ["category_fish"],
                                "RequiredCount": 1,
                            }
                        ],
                        "OutputItem": [{"ItemId": "(O)SmokedFish"}],
                        "MinutesUntilReady": 50,
                    }
                ]
            }
        },
    )


def add_localization_gap_data(game_dir: Path) -> None:
    unpacked_dir = game_dir / "Content (unpacked)"
    add_localized_recipe_items(unpacked_dir)
    write_json(
        unpacked_dir / "Data" / "Furniture.json",
        {"0": "Oak Chair/chair/-1/-1/4/350/-1/[LocalizedText Strings\\Furniture:OakChair]"},
    )
    write_json(unpacked_dir / "Strings" / "Furniture.json", {"OakChair": "Oak Chair"})
    write_json(unpacked_dir / "Strings" / "Furniture.zh-CN.json", {"OakChair": "橡木椅子"})
    write_json(
        unpacked_dir / "Data" / "SpecialOrders.json",
        {"Caroline": {"Name": "[Caroline_Name]", "Text": "[Caroline_Text]"}},
    )
    write_json(
        unpacked_dir / "Strings" / "SpecialOrderStrings.json",
        {"Caroline_Name": "Island Ingredients", "Caroline_Text": "Ship 100 island crops."},
    )
    write_json(
        unpacked_dir / "Strings" / "SpecialOrderStrings.zh-CN.json",
        {"Caroline_Name": "岛屿食材", "Caroline_Text": "请售出 100 份岛屿作物。"},
    )


def add_localized_recipe_items(unpacked_dir: Path) -> None:
    add_recipe_data(unpacked_dir)
    add_misc_localized_entities(unpacked_dir)


def add_recipe_data(unpacked_dir: Path) -> None:
    merge_json(
        unpacked_dir / "Data" / "Objects.json",
        {
            "223": object_data("Cookies", "Cookies", 0),
            "322": object_data("Wood Fence", "WoodFence", 0),
        },
    )
    merge_json(
        unpacked_dir / "Strings" / "Objects.json",
        {"Cookies_Name": "Cookies", "WoodFence_Name": "Wood Fence"},
    )
    merge_json(
        unpacked_dir / "Strings" / "Objects.zh-CN.json",
        {"Cookies_Name": "曲奇", "WoodFence_Name": "木栅栏"},
    )
    write_json(
        unpacked_dir / "Data" / "CookingRecipes.json",
        {"Cookies": "246 1/3 7/223/null/"},
    )
    write_json(
        unpacked_dir / "Data" / "CraftingRecipes.json",
        {"Wood Fence": "388 2/Field/322/false/default/"},
    )


def add_misc_localized_entities(unpacked_dir: Path) -> None:
    write_json(unpacked_dir / "Data" / "TailoringRecipes.json", {"(H)43": {"Id": "(H)43"}})
    write_json(
        unpacked_dir / "Data" / "MonsterSlayerQuests.json",
        {
            "Bats": {
                "DisplayName": "[LocalizedText Strings\\\\Locations:AdventureGuild_KillList_Bats]"
            }
        },
    )
    write_json(
        unpacked_dir / "Strings" / "Locations.json",
        {"AdventureGuild_KillList_Bats": "Bats"},
    )
    write_json(
        unpacked_dir / "Strings" / "Locations.zh-CN.json",
        {
            "AdventureGuild_KillList_Bats": "蝙蝠",
            "CommunityCenter_AreaName_CraftsRoom": "工艺室",
        },
    )
    merge_json(
        unpacked_dir / "Strings" / "Locations.json",
        {"CommunityCenter_AreaName_CraftsRoom": "Crafts Room"},
    )
    write_json(
        unpacked_dir / "Data" / "RandomBundles.json",
        {"0": {"AreaName": "Crafts Room"}},
    )
    merge_json(unpacked_dir / "Data" / "Shops.json", {"AdventureShop": {"Items": []}})
    write_json(unpacked_dir / "Data" / "Characters.json", {"???": {"DisplayName": "???"}})
    write_json(unpacked_dir / "Characters" / "schedules" / "Abigail.json", {"11": "Town 0 0 2"})


def merge_json(path: Path, values: dict[str, object]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(values)
    write_json(path, payload)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def write_image(path: Path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (255, 0, 0, 255)).save(path)


def monster_record(display_name: str) -> str:
    return f"24/5/0/0/false/1000/66 .5/1/.01/4/2/.00/true/3/{display_name}"
