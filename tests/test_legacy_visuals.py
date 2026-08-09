from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from builder.models import DiscoveredJsonFile, NormalizedEntity
from builder.parsers.legacy_visuals import furniture_size
from builder.parsers.official import parse_official_file
from builder.pipeline.images import materialize_entity_images_with_report
from builder.pipeline.normalize import normalize_entities


def test_legacy_visual_records_use_their_real_sprite_metadata(tmp_path: Path) -> None:
    entities = normalized_visual_entities()
    by_id = {entity.id: entity for entity in entities}

    assert by_id["achievement:0"].extra_json["imageRect"] == [192, 128, 64, 64]
    assert by_id["villager:Abigail"].extra_json["imageRect"] == [0, 0, 64, 64]
    assert by_id["object:1"].extra_json["imageGridCellSize"] == [16, 16]
    assert by_id["footwear:1"].extra_json["spriteIndex"] == 1
    assert by_id["big_craftable:1"].extra_json["imageGridCellSize"] == [16, 32]
    assert by_id["furniture:0"].extra_json["imageSize"] == [16, 32]
    assert by_id["furniture:1"].extra_json["imageSize"] == [32, 48]

    asset_root = tmp_path / "assets"
    write_visual_assets(asset_root)
    result = materialize_entity_images_with_report(entities, asset_root, tmp_path / "output")

    assert result.errors == []
    assert image_sizes(tmp_path / "output") == {
        "achievement-0.webp": (64, 64),
        "big_craftable-1.webp": (16, 32),
        "object-1.webp": (16, 16),
        "footwear-1.webp": (16, 16),
        "furniture-0.webp": (16, 32),
        "furniture-1.webp": (32, 48),
        "villager-Abigail.webp": (64, 64),
    }


def test_villager_character_fallback_keeps_its_actual_canvas(tmp_path: Path) -> None:
    entities = normalize_entities(
        parse_entities(
            "villager",
            {"Mariner": {"Name": "Mariner"}},
            {"Mariner": {"Name": "Mariner"}},
        ),
        aliases={},
        categories={},
    )
    asset_root = tmp_path / "assets"
    write_image(asset_root / "Characters" / "Mariner.png", (16, 32), (2, 3, 10, 24))

    result = materialize_entity_images_with_report(entities, asset_root, tmp_path / "output")

    assert result.errors == []
    assert image_sizes(tmp_path / "output") == {"villager-Mariner.webp": (16, 32)}


def test_tools_use_menu_sprite_index_for_static_icons(tmp_path: Path) -> None:
    entities = normalize_entities(
        parse_entities(
            "tool",
            {
                "WateringCan": {
                    "Name": "Watering Can",
                    "DisplayName": "Watering Can",
                    "Texture": r"TileSheets\tools",
                    "SpriteIndex": 273,
                    "MenuSpriteIndex": 296,
                }
            },
            {},
        ),
        aliases={},
        categories={},
    )
    tool = next(entity for entity in entities if entity.id == "tool:WateringCan")
    assert tool.extra_json["spriteIndex"] == 296
    assert tool.extra_json["imageGridCellSize"] == [16, 16]
    assert tool.extra_json["imageSize"] == [16, 16]
    assert tool.extra_json["imageMode"] == "sprite"

    asset_root = tmp_path / "assets"
    image = Image.new("RGBA", (512, 176), (0, 0, 0, 0))
    image.paste((255, 0, 0, 255), (128, 144, 144, 160))
    asset_root.joinpath("TileSheets").mkdir(parents=True)
    image.save(asset_root / "TileSheets" / "tools.png")
    result = materialize_entity_images_with_report(entities, asset_root, tmp_path / "output")

    assert result.errors == []
    output = Image.open(tmp_path / "output" / "images" / "tool-WateringCan.webp").convert("RGBA")
    assert output.getchannel("A").getbbox() is not None


def test_tools_fall_back_to_sprite_index_when_menu_index_is_negative() -> None:
    entities = parse_entities(
        "tool",
        {
            "MilkPail": {
                "Name": "Milk Pail",
                "DisplayName": "Milk Pail",
                "Texture": r"TileSheets\tools",
                "SpriteIndex": 6,
                "MenuSpriteIndex": -1,
            }
        },
        {},
    )
    assert entities[0].attributes["spriteIndex"] == 6


def test_achievements_share_the_official_collections_cursor_tile() -> None:
    entities = normalize_entities(
        parse_entities(
            "achievement",
            {
                "0": "Greenhorn^Earn 15,000g.^true^-1^18",
                "1": "Cowpoke^Earn 50,000g.^true^-1^19",
            },
            {
                "0": "新手^赚取 15,000 金。^true^-1^18",
                "1": "牛仔^赚取 50,000 金。^true^-1^19",
            },
        ),
        aliases={},
        categories={},
    )

    assert {entity.extra_json["imageSource"] for entity in entities} == {
        "LooseSprites/Cursors.png"
    }
    assert {tuple(entity.extra_json["imageRect"]) for entity in entities} == {
        (192, 128, 64, 64)
    }


def test_fully_transparent_optional_image_is_not_materialized(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(asset_root / "blank.png")
    entity = normalized_entity(
        "object:blank",
        {"imageSource": "blank.png", "imageMode": "sprite", "spriteIndex": 0},
    )

    result = materialize_entity_images_with_report([entity], asset_root, tmp_path / "out")

    assert result.errors == []
    assert result.entities[0].image_path is None
    assert result.entities[0].extra_json["imageAvailability"] == "not_applicable"
    assert not (tmp_path / "out" / "images" / "object-blank.webp").exists()


def test_fully_transparent_required_image_is_reported(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(asset_root / "blank.png")
    entity = normalized_entity(
        "achievement:blank",
        {
            "imageSource": "blank.png",
            "imageMode": "sprite",
            "spriteIndex": 0,
            "imageRequired": True,
        },
    )

    result = materialize_entity_images_with_report([entity], asset_root, tmp_path / "out")

    assert result.entities == [entity]
    assert result.errors[0]["reason"] == "必需图片内容完全透明"


def test_required_image_without_source_is_reported(tmp_path: Path) -> None:
    entity = normalized_entity("achievement:missing", {"imageRequired": True})

    result = materialize_entity_images_with_report([entity], tmp_path / "assets", tmp_path / "out")

    assert result.entities == [entity]
    assert result.errors == [
        {
            "source": "image",
            "source_file": "Data/test.json",
            "entity_id": "achievement:missing",
            "asset": "imageSource",
            "reason": "声明了必需图片但未提供 imageSource",
        }
    ]


def test_hidden_non_social_villager_is_not_expected_to_have_a_portrait() -> None:
    entities = parse_entities(
        "villager",
        {"Welwick": hidden_villager()},
        {"Welwick": hidden_villager()},
    )
    normal = parse_entities("villager", {"Abigail": {"Name": "Abigail"}}, {})[0]

    welwick = entities[0]
    assert welwick.attributes["imageAvailability"] == "not_applicable"
    assert "imageSource" not in welwick.attributes
    assert "imageRequired" not in welwick.attributes
    assert normal.attributes["imageSource"] == "Portraits/Abigail.png"
    assert normal.attributes["imageRequired"] is True


@pytest.mark.parametrize(
    ("furniture_type", "expected"),
    [
        ("chair", (1, 2)),
        ("bench", (2, 2)),
        ("couch", (3, 2)),
        ("armchair", (2, 2)),
        ("dresser", (2, 2)),
        ("long table", (5, 3)),
        ("painting", (2, 2)),
        ("lamp", (1, 2)),
        ("bookcase", (1, 2)),
        ("table", (2, 3)),
        ("rug", (2, 3)),
        ("window", (3, 2)),
        ("fireplace", (2, 5)),
        ("torch", (1, 2)),
        ("sconce", (1, 2)),
    ],
)
def test_legacy_furniture_default_sizes(
    furniture_type: str, expected: tuple[int, int]
) -> None:
    assert furniture_size(furniture_type, "-1") == expected


def normalized_visual_entities() -> list[NormalizedEntity]:
    raw_entities = [
        *parse_entities(
            "achievement",
            {"0": "Greenhorn^Earn 15,000g.^true^-1^18"},
            {"0": "新手^赚取 15,000 金。^true^-1^18"},
        ),
        *parse_entities(
            "footwear",
            {"1": "Sneakers/A little flimsy./50/1/0/0/Sneakers"},
            {"1": "Sneakers/有点单薄。/50/1/0/0/运动鞋"},
        ),
        *parse_entities(
            "object", {"1": object_record("Stone")}, {"1": object_record("石头")}
        ),
        *parse_entities(
            "villager", {"Abigail": {"Name": "Abigail"}}, {"Abigail": {"Name": "Abigail"}}
        ),
        *parse_entities(
            "big_craftable", {"1": big_craftable("Keg")}, {"1": big_craftable("小桶")}
        ),
        *parse_entities(
            "furniture",
            furniture_records("Oak Chair", "Custom Table"),
            furniture_records("橡木椅子", "定制桌"),
        ),
    ]
    return normalize_entities(raw_entities, aliases={}, categories={})


def object_record(display_name: str) -> dict[str, object]:
    return {
        "Name": "Stone",
        "DisplayName": display_name,
        "Description": "A stone.",
        "Texture": None,
        "SpriteIndex": 1,
    }


def parse_entities(
    entity_type: str, english: dict[str, object], chinese: dict[str, object]
) -> list:
    return [
        *parse_official_file(discovered_file(entity_type, "en"), english),
        *parse_official_file(discovered_file(entity_type, "zh-CN"), chinese),
    ]


def discovered_file(entity_type: str, locale: str) -> DiscoveredJsonFile:
    suffix = "" if locale == "en" else f".{locale}"
    return DiscoveredJsonFile(
        path=f"Data/{entity_type}{suffix}.json", entity_type=entity_type, locale=locale
    )


def big_craftable(display_name: str) -> dict[str, object]:
    return {
        "Name": "Keg",
        "DisplayName": display_name,
        "Description": "A keg.",
        "Texture": None,
        "SpriteIndex": 1,
    }


def furniture_records(chair_name: str, table_name: str) -> dict[str, str]:
    return {
        "0": f"Oak Chair/chair/-1/-1/4/350/-1/{chair_name}",
        "1": f"Custom Table/table/2 3/-1/4/350/-1/{table_name}/0/TileSheets\\custom_furniture",
    }


def write_visual_assets(asset_root: Path) -> None:
    write_image(asset_root / "LooseSprites" / "Cursors.png", (256, 192), (192, 128, 64, 64))
    write_image(asset_root / "Maps" / "springobjects.png", (32, 16), (16, 0, 16, 16))
    write_image(asset_root / "Portraits" / "Abigail.png", (128, 128), (4, 5, 56, 54))
    write_image(asset_root / "TileSheets" / "Craftables.png", (32, 32), (16, 0, 16, 32))
    write_image(asset_root / "TileSheets" / "furniture.png", (16, 32), (0, 0, 16, 32))
    write_image(asset_root / "TileSheets" / "custom_furniture.png", (32, 48), (0, 0, 32, 48))


def write_image(path: Path, size: tuple[int, int], rect: tuple[int, int, int, int]) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    x, y, width, height = rect
    image.paste((255, 0, 0, 255), (x, y, x + width, y + height))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def image_sizes(output_dir: Path) -> dict[str, tuple[int, int]]:
    return {
        path.name: Image.open(path).size
        for path in sorted((output_dir / "images").glob("*.webp"))
    }


def normalized_entity(entity_id: str, extra_json: dict[str, object]) -> NormalizedEntity:
    return NormalizedEntity(
        id=entity_id,
        entity_type="achievement",
        game_id="missing",
        internal_name=None,
        name_zh="缺失",
        name_en=None,
        description_zh=None,
        description_en=None,
        category=None,
        extra_json=extra_json,
        source_file="Data/test.json",
    )


def hidden_villager() -> dict[str, object]:
    return {
        "Name": "Welwick",
        "TextureName": None,
        "SocialTab": "HiddenAlways",
        "CanSocialize": False,
    }
