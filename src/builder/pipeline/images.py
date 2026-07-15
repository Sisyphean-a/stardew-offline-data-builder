from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from builder.models import NormalizedEntity
from builder.utils.images import (
    create_thumbnail,
    crop_transparent_bounds,
    save_lossless_webp,
)


def materialize_entity_images(
    entities: list[NormalizedEntity],
    asset_root: Path,
    output_dir: Path,
) -> list[NormalizedEntity]:
    images_dir = output_dir / "images"
    if images_dir.exists():
        shutil.rmtree(images_dir)

    updated_entities: list[NormalizedEntity] = []
    for entity in entities:
        image_source = entity.extra_json.get("imageSource")
        image_rect = entity.extra_json.get("imageRect")
        if not isinstance(image_source, str) or not valid_image_rect(image_rect):
            updated_entities.append(entity)
            continue

        absolute_source = asset_root / image_source
        relative_output = Path("images") / f"{sanitize_id(entity.id)}.webp"
        absolute_output = output_dir / relative_output
        build_entity_image(
            source_path=absolute_source,
            image_rect=tuple(int(value) for value in image_rect),
            output_path=absolute_output,
        )
        updated_entities.append(
            entity.model_copy(update={"image_path": relative_output.as_posix()})
        )
    return updated_entities


def build_entity_image(
    source_path: Path,
    image_rect: tuple[int, int, int, int],
    output_path: Path,
) -> None:
    image = Image.open(source_path).convert("RGBA")
    x, y, width, height = image_rect
    sprite = image.crop((x, y, x + width, y + height))
    trimmed = crop_transparent_bounds(sprite)
    thumbnail = create_thumbnail(trimmed, max_size=(96, 96))
    save_lossless_webp(thumbnail, output_path)


def valid_image_rect(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
    )


def sanitize_id(entity_id: str) -> str:
    return entity_id.replace(":", "-").replace("/", "-")
