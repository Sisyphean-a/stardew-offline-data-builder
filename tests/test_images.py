from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from builder.models import NormalizedEntity
from builder.pipeline import images as image_pipeline
from builder.pipeline.images import (
    build_entity_image,
    crop_image,
    materialize_entity_images_with_report,
)
from builder.utils.images import (
    create_thumbnail,
    crop_transparent_bounds,
    save_lossless_webp,
    split_sprite_sheet,
)


def test_crop_transparent_bounds_removes_outer_padding() -> None:
    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    for x in range(2, 8):
        for y in range(3, 9):
            image.putpixel((x, y), (255, 0, 0, 255))

    cropped = crop_transparent_bounds(image)

    assert cropped.size == (6, 6)


def test_split_sprite_sheet_returns_full_cells_only() -> None:
    image = Image.new("RGBA", (8, 4), (0, 0, 0, 0))
    sprites = split_sprite_sheet(image, cell_width=4, cell_height=4)

    assert len(sprites) == 2
    assert all(sprite.size == (4, 4) for sprite in sprites)


def test_create_thumbnail_keeps_aspect_ratio() -> None:
    image = Image.new("RGBA", (100, 50), (255, 255, 255, 255))

    thumbnail = create_thumbnail(image, max_size=(20, 20))

    assert thumbnail.size == (20, 10)


def test_sprite_thumbnail_uses_nearest_sampling() -> None:
    image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    for x in range(2, 4):
        for y in range(4):
            image.putpixel((x, y), (0, 0, 255, 255))

    thumbnail = create_thumbnail(image, max_size=(2, 2), resampling=Image.Resampling.NEAREST)

    assert thumbnail.getpixel((0, 0)) == (255, 0, 0, 255)
    assert thumbnail.getpixel((1, 0)) == (0, 0, 255, 255)


def test_sprite_materialization_preserves_declared_transparent_canvas(tmp_path: Path) -> None:
    source_path = tmp_path / "sprite.png"
    image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    image.putpixel((1, 1), (255, 0, 0, 255))
    image.save(source_path)

    output_path = tmp_path / "images" / "sprite.webp"
    build_entity_image(source_path, (0, 0, 4, 4), output_path, preserve_canvas=True)

    assert Image.open(output_path).size == (4, 4)


def test_materialization_decodes_each_source_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "source.png"
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(source_path)
    entity = NormalizedEntity(
        id="object:source",
        entity_type="object",
        game_id="source",
        internal_name=None,
        name_zh="来源",
        name_en=None,
        description_zh=None,
        description_en=None,
        category=None,
        extra_json={"imageSource": "source.png", "imageMode": "full"},
        source_file="Data/test.json",
    )
    opened_paths: list[Path] = []
    original_open = image_pipeline.Image.open

    def counting_open(path: str | Path, *args: object, **kwargs: object) -> Image.Image:
        if Path(path) == source_path:
            opened_paths.append(source_path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(image_pipeline.Image, "open", counting_open)

    result = materialize_entity_images_with_report([entity], tmp_path, tmp_path / "output")

    assert result.errors == []
    assert result.entities[0].image_path == "images/object-source.webp"
    assert opened_paths == [source_path]


def test_crop_image_rejects_out_of_bounds_rectangles() -> None:
    image = Image.new("RGBA", (8, 8), (255, 255, 255, 255))

    with pytest.raises(ValueError, match="超出源图边界"):
        crop_image(image, (0, 0, 9, 8))


def test_save_lossless_webp_writes_output(tmp_path: Path) -> None:
    image = Image.new("RGBA", (8, 8), (0, 255, 0, 255))
    output_path = tmp_path / "images" / "sprite.webp"

    save_lossless_webp(image, output_path)

    assert output_path.exists()
    reopened = Image.open(output_path)
    assert reopened.size == (8, 8)
