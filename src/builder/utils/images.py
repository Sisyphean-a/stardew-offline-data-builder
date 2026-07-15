from __future__ import annotations

from pathlib import Path

from PIL import Image


def crop_transparent_bounds(image: Image.Image) -> Image.Image:
    rgba_image = image.convert("RGBA")
    alpha = rgba_image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return rgba_image.copy()
    return rgba_image.crop(bbox)


def split_sprite_sheet(
    image: Image.Image,
    cell_width: int,
    cell_height: int,
) -> list[Image.Image]:
    if cell_width <= 0 or cell_height <= 0:
        raise ValueError("cell size must be positive")

    width, height = image.size
    sprites: list[Image.Image] = []
    for top in range(0, height, cell_height):
        for left in range(0, width, cell_width):
            if left + cell_width > width or top + cell_height > height:
                continue
            sprites.append(image.crop((left, top, left + cell_width, top + cell_height)))
    return sprites


def create_thumbnail(
    image: Image.Image,
    max_size: tuple[int, int],
) -> Image.Image:
    thumbnail = image.copy()
    thumbnail.thumbnail(max_size, Image.Resampling.LANCZOS)
    return thumbnail


def save_lossless_webp(image: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="WEBP", lossless=True, method=6)
