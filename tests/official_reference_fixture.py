from __future__ import annotations

from pathlib import Path

from tests.real_official_entities import object_data
from tests.real_official_fixture import merge_json, write_json


def add_reference_edge_cases(unpacked_dir: Path) -> None:
    add_item_records(unpacked_dir)
    add_shop_edge_cases(unpacked_dir)
    add_recipe_edge_cases(unpacked_dir)
    add_machine_edge_cases(unpacked_dir)


def add_item_records(unpacked_dir: Path) -> None:
    merge_json(
        unpacked_dir / "Data" / "Objects.json",
        {
            "Moss": item_data("Moss", -16, ["color_green"]),
            "685": item_data("Bait", -21, []),
            "66": item_data("Amethyst", -2, ["color_purple"], "Minerals"),
            "74": item_data(
                "Prismatic Shard",
                -2,
                ["color_prismatic", "crystalarium_banned"],
                "Minerals",
            ),
            "BannedSeed": item_data("Banned Seed", -75, ["seedmaker_banned"]),
        },
    )
    write_json(
        unpacked_dir / "Data" / "Boots.json",
        {"504": "Sneakers/A little flimsy/50/1/0/0/Sneakers"},
    )


def item_data(
    name: str,
    category: int,
    tags: list[str],
    item_type: str = "Basic",
) -> dict[str, object]:
    data = object_data(name, name.replace(" ", ""), 0, item_type)
    return {
        **data,
        "DisplayName": name,
        "Description": f"{name} description",
        "Category": category,
        "ContextTags": tags,
    }


def add_shop_edge_cases(unpacked_dir: Path) -> None:
    merge_json(
        unpacked_dir / "Data" / "Shops.json",
        {
            "ReferenceShop": {
                "Items": [
                    {"ItemId": "Moss", "Price": 100, "AvailableStock": -1},
                    {"ItemId": "(B)504", "Price": 500, "AvailableStock": 1},
                    {
                        "RandomItemId": ["(O)24", "(O)Moss"],
                        "Id": "RandomProduce",
                        "Price": 750,
                        "AvailableStock": 2,
                        "AvailableStockLimit": "Player",
                        "AvailableStockModifiers": [{"Amount": 1}],
                        "AvailableStockModifierMode": "Minimum",
                    },
                    {
                        "RandomItemId": [
                            "FLAVORED_ITEM Bait (O)128",
                            "FLAVORED_ITEM Bait (O)129",
                        ],
                        "Id": "RandomFlavoredBait",
                        "Price": 1000,
                    },
                ]
            }
        },
    )


def add_recipe_edge_cases(unpacked_dir: Path) -> None:
    write_json(
        unpacked_dir / "Data" / "CraftingRecipes.json",
        {"Reference Recipe": "Moss 1 -75 2/Home/24/false/default/"},
    )


def add_machine_edge_cases(unpacked_dir: Path) -> None:
    merge_json(
        unpacked_dir / "Data" / "Machines.json",
        {
            "(BC)Crystalarium": machine_data(
                ["category_gem", "!crystalarium_banned"]
            ),
            "(BC)SeedMaker": machine_data(["!seedmaker_banned"]),
        },
    )


def machine_data(required_tags: list[str]) -> dict[str, object]:
    return {
        "OutputRules": [
            {
                "Id": "Default",
                "Triggers": [
                    {
                        "Id": "ItemPlacedInMachine",
                        "RequiredTags": required_tags,
                        "RequiredCount": 1,
                    }
                ],
                "OutputItem": [{"ItemId": "(O)24"}],
            }
        ]
    }
