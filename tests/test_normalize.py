from __future__ import annotations

from pathlib import Path

from builder.models import RawEntity
from builder.pipeline.normalize import normalize_entities
from builder.sources.game_source import load_raw_entities_from_unpacked_dir


def test_crop_inherits_harvest_object_image_metadata() -> None:
    entities = normalize_entities(
        [
            RawEntity(
                source="official",
                entity_type="object",
                source_id="24",
                internal_name="Parsnip",
                name="Parsnip",
                description=None,
                locale="en",
                attributes={
                    "imageSource": "Maps/springobjects.png",
                    "spriteIndex": 42,
                    "imageGridCellSize": [16, 16],
                    "imageSize": [16, 16],
                    "imageMode": "sprite",
                },
                source_file="Data/Objects.json",
            ),
            RawEntity(
                source="official",
                entity_type="crop",
                source_id="24",
                internal_name="Parsnip",
                name="Parsnip",
                description=None,
                locale="en",
                attributes={
                    "HarvestItemId": "24",
                    "Texture": "TileSheets/crops",
                    "SpriteIndex": 0,
                    "officialDerived": {"growDays": 4},
                },
                source_file="Data/Crops.json",
            ),
        ],
        aliases={},
        categories={},
    )

    crop = next(entity for entity in entities if entity.entity_type == "crop")
    assert crop.extra_json["imageSource"] == "Maps/springobjects.png"
    assert crop.extra_json["spriteIndex"] == 42
    assert crop.extra_json["officialDerived"] == {"growDays": 4}
    assert crop.extra_json["_provenance"] == {
        "official": ["Data/Crops.json", "Data/Objects.json"]
    }


def test_normalize_fixture_entities() -> None:
    raw_entities = load_raw_entities_from_unpacked_dir(
        Path("tests/fixtures/game-data/Content (unpacked)")
    )

    entities = normalize_entities(
        raw_entities,
        aliases={"object:24": ["萝卜"]},
        categories={"object:24": "作物"},
    )

    assert {entity.id for entity in entities} == {
        "object:24",
        "crop:kale-seeds",
        "fish:sturgeon",
        "villager:Abigail",
        "achievement:0",
        "big_craftable:0",
        "footwear:504",
        "furniture:0",
    }

    object_entity = next(entity for entity in entities if entity.id == "object:24")
    assert object_entity.name_zh == "防风草"
    assert object_entity.name_en == "Parsnip"
