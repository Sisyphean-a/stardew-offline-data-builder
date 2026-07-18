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
        "footwear-1.webp": (16, 16),
        "furniture-0.webp": (16, 32),
        "furniture-1.webp": (32, 48),
    }


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
        ("fireplace", (1, 2)),
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
            "big_craftable", {"1": big_craftable("Keg")}, {"1": big_craftable("小桶")}
        ),
        *parse_entities(
            "furniture",
            furniture_records("Oak Chair", "Custom Table"),
            furniture_records("橡木椅子", "定制桌"),
        ),
    ]
    return normalize_entities(raw_entities, aliases={}, categories={})


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
