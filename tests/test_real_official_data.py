from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from builder.cli import app
from builder.models import MatchResult
from builder.pipeline.merge import merge_official_and_community
from builder.pipeline.normalize import normalize_entities
from builder.sources.community_source import load_community_data_from_dir
from builder.sources.game_source import load_game_data_from_unpacked_dir

runner = CliRunner()


def test_real_official_layout_builds_primary_entities(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    output_dir = tmp_path / "output"

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
        connection.execute("SELECT id, name_zh FROM entities WHERE id IN (?, ?, ?, ?)", (
            "object:24",
            "crop:24",
            "fish:128",
            "villager:Abigail",
        )).fetchall()
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


def test_real_community_arrays_are_loaded_and_do_not_override_official(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    community_dir = tmp_path / "community"
    community_dir.mkdir()
    write_json(
        community_dir / "artifacts.json",
        [{"id": "24", "name": "Parsnip", "description": "Community", "price": 35}],
    )

    official = load_game_data_from_unpacked_dir(game_dir / "Content (unpacked)")
    community = load_community_data_from_dir(community_dir)
    official_entities = normalize_entities(official.entities, aliases={}, categories={})
    community_entities = normalize_entities(community.entities, aliases={}, categories={})
    merged = merge_official_and_community(
        official_entities,
        community_entities,
        {"object:24": MatchResult(entity_id="object:24", matched_by="stable_id")},
    )

    parsnip = next(entity for entity in merged if entity.id == "object:24")
    assert len(community.entities) == 1
    assert parsnip.name_zh == "防风草"
    assert parsnip.extra_json["price"] == 35
    assert parsnip.extra_json["_provenance"]["community"] == ["artifacts.json"]


def test_real_official_layout_derives_drops_minerals_and_rings(tmp_path: Path) -> None:
    game_dir = create_real_layout(tmp_path)
    entities = load_game_data_from_unpacked_dir(game_dir / "Content (unpacked)").entities
    normalized = normalize_entities(entities, aliases={}, categories={})
    by_id = {entity.id: entity for entity in normalized}

    assert by_id["mineral:66"].name_zh == "紫水晶"
    assert by_id["ring:517"].name_zh == "光辉戒指"
    assert by_id["drop:Green-Slime:0"].name_zh == "紫水晶"


def create_real_layout(tmp_path: Path) -> Path:
    game_dir = tmp_path / "真实游戏"
    unpacked_dir = game_dir / "Content (unpacked)"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    write_json(
        unpacked_dir / "Data" / "Objects.json",
        {
            "24": object_data("Parsnip", "Parsnip", 0),
            "128": object_data("Pufferfish", "Pufferfish", 1),
            "66": object_data("Amethyst", "Amethyst", 0, "Minerals"),
            "517": object_data("Glow Ring", "GlowRing", 1, "Ring"),
        },
    )
    write_json(
        unpacked_dir / "Data" / "Crops.json",
        {"472": {"HarvestItemId": "24", "Texture": "TileSheets\\crops", "SpriteIndex": 0}},
    )
    write_json(unpacked_dir / "Data" / "Fish.json", {"128": "Pufferfish/80/floater"})
    write_json(
        unpacked_dir / "Data" / "Monsters.json",
        {"Green Slime": "24/5/0/0/false/1000/66 .5/1/.01"},
    )
    write_json(
        unpacked_dir / "Data" / "Characters.json",
        {"Abigail": {"DisplayName": "[LocalizedText Strings\\NPCNames:Abigail]"}},
    )
    write_json(
        unpacked_dir / "Strings" / "Objects.json",
        {
            "Parsnip_Name": "Parsnip",
            "Parsnip_Description": "A spring tuber.",
            "Pufferfish_Name": "Pufferfish",
            "Pufferfish_Description": "Inflates when threatened.",
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
            "Amethyst_Name": "紫水晶",
            "Amethyst_Description": "一种紫色水晶。",
            "GlowRing_Name": "光辉戒指",
            "GlowRing_Description": "提供光亮。",
        },
    )
    write_json(unpacked_dir / "Strings" / "NPCNames.json", {"Abigail": "Abigail"})
    write_json(unpacked_dir / "Strings" / "NPCNames.zh-CN.json", {"Abigail": "阿比盖尔"})
    write_image(unpacked_dir / "Maps" / "springobjects.png", (32, 16))
    write_image(unpacked_dir / "TileSheets" / "crops.png", (16, 16))
    write_image(unpacked_dir / "Portraits" / "Abigail.png", (32, 64))
    return game_dir


def object_data(
    name: str,
    text_key: str,
    sprite_index: int,
    item_type: str = "Basic",
) -> dict[str, object]:
    return {
        "Name": name,
        "DisplayName": f"[LocalizedText Strings\\Objects:{text_key}_Name]",
        "Description": f"[LocalizedText Strings\\Objects:{text_key}_Description]",
        "Price": 40,
        "Type": item_type,
        "Texture": None,
        "SpriteIndex": sprite_index,
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def write_image(path: Path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (255, 0, 0, 255)).save(path)
