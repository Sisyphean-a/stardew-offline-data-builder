from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from builder.cli import app
from builder.config import EXIT_PACKAGE
from builder.pipeline.normalize import normalize_entities
from builder.pipeline.official_enrichment import enrich_official_entities
from builder.sources.game_source import load_game_data_from_unpacked_dir
from tests.complete_fixture import add_required_entity_baseline
from tests.official_reference_fixture import add_reference_edge_cases
from tests.real_official_fixture import (
    add_localization_gap_data,
    create_real_layout,
    write_image,
    write_json,
)

runner = CliRunner()


def test_real_official_layout_builds_primary_entities(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    output_dir = tmp_path / "output"
    add_legacy_visual_records(game_dir / "Content (unpacked)")
    add_required_entity_baseline(game_dir / "Content (unpacked)")

    result = runner.invoke(
        app,
        [
            "build",
            "--game-dir",
            str(game_dir),
            "--unpacked-dir",
            str(game_dir / "Content (unpacked)"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    connection = sqlite3.connect(output_dir / "stardew.db")
    rows = dict(
        connection.execute(
            "SELECT id, name_zh FROM entities WHERE id IN (?, ?, ?, ?)",
            ("object:24", "crop:24", "fish:128", "villager:Abigail"),
        ).fetchall()
    )
    price = connection.execute(
        "SELECT extra_json FROM entities WHERE id = 'object:24'"
    ).fetchone()
    connection.close()

    assert rows == {
        "object:24": "防风草",
        "crop:24": "防风草",
        "fish:128": "河豚",
        "villager:Abigail": "阿比盖尔",
    }
    assert json.loads(price[0])["Price"] == 40
    assert (output_dir / "images" / "object-24.webp").exists()
    assert (output_dir / "reports" / "coverage.json").exists()


def test_real_legacy_visual_records_build_with_required_images(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    unpacked_dir = game_dir / "Content (unpacked)"
    add_legacy_visual_records(unpacked_dir)
    add_required_entity_baseline(unpacked_dir)
    output_dir = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "build",
            "--game-dir",
            str(game_dir),
            "--unpacked-dir",
            str(unpacked_dir),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    connection = sqlite3.connect(output_dir / "stardew.db")
    rows = dict(
        connection.execute(
            "SELECT id, name_zh FROM entities WHERE id IN (?, ?, ?, ?)",
            ("achievement:0", "footwear:504", "big_craftable:0", "furniture:0"),
        ).fetchall()
    )
    connection.close()
    coverage = json.loads((output_dir / "reports" / "coverage.json").read_text())
    errors = json.loads((output_dir / "reports" / "errors.json").read_text())

    assert rows == {
        "achievement:0": "新手",
        "footwear:504": "运动鞋",
        "big_craftable:0": "小桶",
        "furniture:0": "橡木椅",
    }
    assert all(
        (output_dir / "images" / filename).exists()
        for filename in (
            "achievement-0.webp",
            "footwear-504.webp",
            "big_craftable-0.webp",
            "furniture-0.webp",
        )
    )
    assert coverage["images"]["expected"] == 4
    assert coverage["images"]["materialized"] == 4
    assert errors == []
    assert (output_dir / "stardew-zh-CN.svdata").exists()


def test_standalone_package_rejects_missing_required_image(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    unpacked_dir = game_dir / "Content (unpacked)"
    add_legacy_visual_records(unpacked_dir)
    add_required_entity_baseline(unpacked_dir)
    output_dir = tmp_path / "output"
    initial = runner.invoke(
        app,
        [
            "build",
            "--game-dir",
            str(game_dir),
            "--unpacked-dir",
            str(unpacked_dir),
            "--output",
            str(output_dir),
        ],
    )
    package_path = output_dir / "stardew-zh-cn.svdata"
    package_hash = package_path.read_bytes()
    (output_dir / "images" / "achievement-0.webp").unlink()

    package = runner.invoke(app, ["package", "--output", str(output_dir)])

    assert initial.exit_code == 0, initial.output
    assert package.exit_code == EXIT_PACKAGE
    assert "图片文件缺失：achievement:0" in package.stdout
    assert package_path.read_bytes() == package_hash


def add_legacy_visual_records(unpacked_dir: Path) -> None:
    records = {
        "Achievements": (
            {"0": "Greenhorn^Earn 15,000g.^true^-1^18"},
            {"0": "新手^赚取 15,000 金。^true^-1^18"},
        ),
        "Boots": (
            {"504": "Sneakers/A little flimsy./50/1/0/0/Sneakers"},
            {"504": "Sneakers/有点单薄。/50/1/0/0/运动鞋"},
        ),
        "BigCraftables": (
            {
                "0": {
                    "Name": "Keg",
                    "DisplayName": "Keg",
                    "Description": "A keg.",
                    "Texture": None,
                    "SpriteIndex": 0,
                }
            },
            {
                "0": {
                    "Name": "Keg",
                    "DisplayName": "小桶",
                    "Description": "一个小桶。",
                    "Texture": None,
                    "SpriteIndex": 0,
                }
            },
        ),
        "Furniture": (
            {"0": "Oak Chair/chair/-1/-1/4/350/-1/Oak Chair"},
            {"0": "Oak Chair/chair/-1/-1/4/350/-1/橡木椅"},
        ),
    }
    for filename, (english, chinese) in records.items():
        write_json(unpacked_dir / "Data" / f"{filename}.json", english)
        write_json(unpacked_dir / "Data" / f"{filename}.zh-CN.json", chinese)
    write_json(
        unpacked_dir / "Data" / "Characters.json",
        {
            "Abigail": {
                "DisplayName": "[LocalizedText Strings\\NPCNames:Abigail]",
                "TextureName": None,
                "SocialTab": "HiddenAlways",
                "CanSocialize": False,
            }
        },
    )
    write_image(unpacked_dir / "LooseSprites" / "Cursors.png", (256, 192))
    write_image(unpacked_dir / "Maps" / "springobjects.png", (384, 352))
    write_image(unpacked_dir / "TileSheets" / "Craftables.png", (128, 32))
    write_image(unpacked_dir / "TileSheets" / "furniture.png", (512, 32))


def test_missing_official_support_asset_fails_explicitly(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    unpacked_dir = game_dir / "Content (unpacked)"
    (unpacked_dir / "Data" / "Machines.json").unlink()

    with pytest.raises(FileNotFoundError, match="Machines.json"):
        load_game_data_from_unpacked_dir(unpacked_dir)


def test_official_support_assets_enrich_entities(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    official = load_game_data_from_unpacked_dir(game_dir / "Content (unpacked)")
    normalized = normalize_entities(official.entities, aliases={}, categories={})
    enriched = enrich_official_entities(normalized, official.support)
    by_id = {entity.id: entity for entity in enriched}

    crop = by_id["crop:24"].extra_json["officialDerived"]
    fish = by_id["fish:128"].extra_json["officialDerived"]
    parsnip = by_id["object:24"].extra_json["officialDerived"]

    assert crop["growDays"] == 4
    assert crop["seedItemId"] == "472"
    assert crop["seedShopOffers"][0]["shopId"] == "SeedShop"
    assert fish["difficulty"] == 80
    assert fish["locations"][0]["locationId"] == "Beach"
    assert fish["fishPondRules"][0]["ruleId"] == "Pufferfish"
    assert fish["machineUses"][0]["machineId"] == "(BC)FishSmoker"
    assert parsnip["sellPrice"] == 40


def test_real_official_layout_derives_drops_minerals_and_rings(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    entities = load_game_data_from_unpacked_dir(game_dir / "Content (unpacked)").entities
    normalized = normalize_entities(entities, aliases={}, categories={})
    by_id = {entity.id: entity for entity in normalized}

    assert by_id["mineral:66"].name_zh == "紫水晶"
    assert by_id["ring:517"].name_zh == "光辉戒指"
    assert by_id["drop:Green-Slime:0"].name_zh == "紫水晶"


def test_official_references_cover_item_and_tag_edge_cases(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    unpacked_dir = game_dir / "Content (unpacked)"
    add_reference_edge_cases(unpacked_dir)
    official = load_game_data_from_unpacked_dir(unpacked_dir)
    normalized = normalize_entities(official.entities, aliases={}, categories={})
    enriched = enrich_official_entities(normalized, official.support)
    by_id = {entity.id: entity.extra_json.get("officialDerived", {}) for entity in enriched}

    moss = by_id["object:Moss"]
    parsnip = by_id["object:24"]
    shoes = by_id["footwear:504"]
    amethyst = by_id["mineral:66"]
    prismatic = by_id["mineral:74"]
    banned_seed = by_id["object:BannedSeed"]
    bait = by_id["object:685"]

    assert {offer["shopId"] for offer in moss["shopOffers"]} == {"ReferenceShop"}
    random_offer = next(offer for offer in moss["shopOffers"] if "randomItemIds" in offer)
    assert random_offer["availableStock"] == 2
    assert random_offer["availableStockLimit"] == "Player"
    assert random_offer["availableStockModifierMode"] == "Minimum"
    assert len(bait["shopOffers"]) == 1
    assert bait["shopOffers"][0]["offerId"] == "RandomFlavoredBait"
    assert shoes["shopOffers"][0]["itemId"] == "(B)504"
    assert "machineUses" not in shoes
    assert any(use["usageId"] == "crafting_recipe:Reference-Recipe" for use in moss["usedIn"])
    assert any(use["usageId"] == "crafting_recipe:Reference-Recipe" for use in parsnip["usedIn"])
    assert any(use["machineId"] == "(BC)Crystalarium" for use in amethyst["machineUses"])
    assert not any(
        use["machineId"] == "(BC)Crystalarium"
        for use in prismatic.get("machineUses", [])
    )
    assert any(use["machineId"] == "(BC)SeedMaker" for use in moss["machineUses"])
    assert not any(
        use["machineId"] == "(BC)SeedMaker"
        for use in banned_seed.get("machineUses", [])
    )


def test_real_layout_resolves_localized_records_and_filters_technical_keys(
    tmp_path: Path,
) -> None:
    game_dir = create_real_layout(tmp_path)
    add_localization_gap_data(game_dir)

    entities = load_game_data_from_unpacked_dir(game_dir / "Content (unpacked)").entities
    normalized = normalize_entities(entities, aliases={}, categories={})
    by_id = {entity.id: entity for entity in normalized}

    assert by_id["furniture:0"].name_zh == "橡木椅子"
    assert by_id["monster:Green-Slime"].name_zh == "绿色史莱姆"
    assert by_id["special_order:Caroline"].name_zh == "岛屿食材"
    assert by_id["special_order:Caroline"].description_zh == "请售出 100 份岛屿作物。"
    assert by_id["quest:Bats"].name_zh == "蝙蝠"
    assert by_id["bundle:0"].name_zh == "工艺室"
    assert by_id["cooking_recipe:Cookies"].name_zh == "曲奇"
    assert by_id["crafting_recipe:Wood-Fence"].name_zh == "木栅栏"
    assert by_id["npc_schedule:Abigail:11"].translation_status == "not_applicable"
    assert by_id["tailoring_recipe:(H)43"].translation_status == "not_applicable"
    assert by_id["shop:AdventureShop"].translation_status == "not_applicable"
    assert by_id["villager:???"].translation_status == "not_applicable"
