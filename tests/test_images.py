from __future__ import annotations

from pathlib import Path

from PIL import Image

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


def test_save_lossless_webp_writes_output(tmp_path: Path) -> None:
    image = Image.new("RGBA", (8, 8), (0, 255, 0, 255))
    output_path = tmp_path / "images" / "sprite.webp"

    save_lossless_webp(image, output_path)

    assert output_path.exists()
    reopened = Image.open(output_path)
    assert reopened.size == (8, 8)
