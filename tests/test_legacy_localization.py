from __future__ import annotations

import json
from pathlib import Path

from builder.pipeline.normalize import normalize_entities
from builder.sources.game_source import load_game_data_from_unpacked_dir


def test_legacy_records_use_official_localized_display_fields(tmp_path: Path) -> None:
    unpacked_dir = create_legacy_layout(tmp_path)

    entities = load_game_data_from_unpacked_dir(unpacked_dir).entities
    normalized = normalize_entities(entities, aliases={}, categories={})
    by_id = {entity.id: entity for entity in normalized}

    assert by_id["crafting_recipe:Transmute-(Fe)"].name_en == "Transmute (Fe)"
    assert by_id["crafting_recipe:Transmute-(Fe)"].name_zh == "铁锭转换术"
    assert by_id["cooking_recipe:Cookies"].name_zh == "曲奇"
    assert by_id["quest:1"].name_zh == "会见法师"
    assert by_id["quest:1"].description_zh == "去拜访法师。"
    assert by_id["bundle:Pantry/0"].name_zh == "春季作物"


def create_legacy_layout(tmp_path: Path) -> Path:
    unpacked_dir = tmp_path / "Content (unpacked)"
    add_empty_support_files(unpacked_dir)
    write_json(
        unpacked_dir / "Data" / "Objects.json",
        {
            "223": object_data("Cookies", "Cookies"),
            "335": object_data("IronBar", "IronBar"),
        },
    )
    write_json(
        unpacked_dir / "Data" / "CookingRecipes.json",
        {"Cookies": "246 1/3 7/223/null/"},
    )
    write_json(
        unpacked_dir / "Data" / "CraftingRecipes.json",
        {
            "Transmute (Fe)": (
                "334 3/Home/335/false/s Mining 4/"
                "[LocalizedText Strings\\Objects:CraftingRecipe_IronBar]"
            )
        },
    )
    write_json(
        unpacked_dir / "Data" / "Quests.json",
        {"1": "Location/Meet The Wizard/Visit the Wizard."},
    )
    write_json(
        unpacked_dir / "Data" / "Quests.zh-CN.json",
        {"1": "Location/会见法师/去拜访法师。"},
    )
    write_json(
        unpacked_dir / "Data" / "Bundles.json",
        {"Pantry/0": "Spring Crops/24 1 188 1/0///Spring Crops"},
    )
    write_json(
        unpacked_dir / "Data" / "Bundles.zh-CN.json",
        {"Pantry/0": "春季作物/24 1 188 1/0///春季作物"},
    )
    add_legacy_localizations(unpacked_dir)
    return unpacked_dir


def add_empty_support_files(unpacked_dir: Path) -> None:
    write_json(unpacked_dir / "Data" / "FishPondData.json", [])
    write_json(unpacked_dir / "Data" / "Locations.json", {})
    write_json(unpacked_dir / "Data" / "Machines.json", {})
    write_json(unpacked_dir / "Data" / "Shops.json", {})


def add_legacy_localizations(unpacked_dir: Path) -> None:
    write_json(
        unpacked_dir / "Strings" / "Objects.json",
        {
            "Cookies_Name": "Cookies",
            "IronBar_Name": "Iron Bar",
            "CraftingRecipe_IronBar": "Transmute (Fe)",
        },
    )
    write_json(
        unpacked_dir / "Strings" / "Objects.zh-CN.json",
        {
            "Cookies_Name": "曲奇",
            "IronBar_Name": "铁锭",
            "CraftingRecipe_IronBar": "铁锭转换术",
        },
    )


def object_data(name: str, text_key: str) -> dict[str, object]:
    return {
        "Name": name,
        "DisplayName": f"[LocalizedText Strings\\Objects:{text_key}_Name]",
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
