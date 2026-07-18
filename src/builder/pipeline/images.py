from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from builder.models import NormalizedEntity
from builder.utils.images import (
    create_thumbnail,
    crop_transparent_bounds,
    save_lossless_webp,
)

INVALID_FILENAME_CHARACTERS = re.compile(r'[<>:"/\\|?*]')


@dataclass
class ImageMaterialization:
    entities: list[NormalizedEntity] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def materialize_entity_images(
    entities: list[NormalizedEntity], asset_root: Path, output_dir: Path
) -> list[NormalizedEntity]:
    return materialize_entity_images_with_report(entities, asset_root, output_dir).entities


def materialize_entity_images_with_report(
    entities: list[NormalizedEntity], asset_root: Path, output_dir: Path
) -> ImageMaterialization:
    images_dir = output_dir / "images"
    clear_previous_images(images_dir, output_dir)
    asset_index = build_asset_index(asset_root)
    result = ImageMaterialization()
    for entity in entities:
        materialize_entity(entity, asset_root, asset_index, output_dir, result)
    return result


def materialize_entity(
    entity: NormalizedEntity,
    asset_root: Path,
    asset_index: dict[str, Path],
    output_dir: Path,
    result: ImageMaterialization,
) -> None:
    image_source = entity.extra_json.get("imageSource")
    if not isinstance(image_source, str) or not image_source:
        if entity.extra_json.get("imageRequired") is True:
            result.errors.append(
                image_error(entity, "imageSource", "声明了必需图片但未提供 imageSource")
            )
        result.entities.append(entity)
        return
    source_path = resolve_image_source(entity.extra_json, asset_root, image_source, asset_index)
    if source_path is None:
        result.errors.append(image_error(entity, image_source, "未找到官方图片资源"))
        result.entities.append(entity)
        return
    image_rect = image_rect_for(entity.extra_json, source_path)
    relative_output = Path("images") / f"{sanitize_id(entity.id)}.webp"
    try:
        build_entity_image(source_path, image_rect, output_dir / relative_output)
    except Exception as exc:
        result.errors.append(image_error(entity, image_source, str(exc)))
        result.entities.append(entity)
        return
    result.entities.append(entity.model_copy(update={"image_path": relative_output.as_posix()}))


def clear_previous_images(images_dir: Path, output_dir: Path) -> None:
    if not images_dir.exists():
        return
    images_dir.resolve().relative_to(output_dir.resolve())
    shutil.rmtree(images_dir)


def build_asset_index(asset_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in asset_root.rglob("*.png"):
        index[path.relative_to(asset_root).as_posix().lower()] = path
        index.setdefault(f"@{normalized_filename(path.name)}", path)
    return index


def resolve_image_source(
    attributes: dict[str, object],
    asset_root: Path,
    image_source: str,
    asset_index: dict[str, Path],
) -> Path | None:
    candidates = [image_source, *fallback_sources(attributes)]
    for candidate in candidates:
        source_path = resolve_asset_path(asset_root, candidate, asset_index)
        if source_path is not None:
            return source_path
    return None


def resolve_asset_path(
    asset_root: Path, image_source: str, asset_index: dict[str, Path]
) -> Path | None:
    normalized = image_source.replace("\\", "/").lstrip("/")
    candidate = (asset_root / normalized).resolve()
    try:
        candidate.relative_to(asset_root.resolve())
    except ValueError:
        return None
    if candidate.exists():
        return candidate
    return asset_index.get(normalized.lower()) or asset_index.get(
        f"@{normalized_filename(Path(normalized).name)}"
    )


def fallback_sources(attributes: dict[str, object]) -> list[str]:
    value = attributes.get("imageFallbackSources")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def normalized_filename(value: str) -> str:
    return Path(value).stem.lower().replace("_", "").replace("-", "").replace(" ", "")


def image_rect_for(
    attributes: dict[str, object], source_path: Path
) -> tuple[int, int, int, int] | None:
    image_rect = attributes.get("imageRect")
    if valid_image_rect(image_rect):
        return tuple(int(value) for value in image_rect)
    sprite_index = attributes.get("spriteIndex")
    if isinstance(sprite_index, int) and attributes.get("imageMode") != "full":
        grid_width, grid_height = image_metadata_size(
            attributes, "imageGridCellSize", (16, 16)
        )
        image_width, image_height = image_metadata_size(
            attributes, "imageSize", (grid_width, grid_height)
        )
        return sprite_index_rect(
            source_path,
            sprite_index,
            grid_width,
            grid_height,
            image_width,
            image_height,
        )
    return None


def image_metadata_size(
    attributes: dict[str, object], key: str, default: tuple[int, int]
) -> tuple[int, int]:
    value = attributes.get(key)
    if value is None:
        return default
    if not valid_image_size(value):
        raise ValueError(f"{key} 必须是两个正整数")
    return int(value[0]), int(value[1])


def sprite_index_rect(
    source_path: Path,
    sprite_index: int,
    grid_width: int = 16,
    grid_height: int = 16,
    image_width: int = 16,
    image_height: int = 16,
) -> tuple[int, int, int, int]:
    with Image.open(source_path) as image:
        columns = max(1, image.width // grid_width)
    return (
        (sprite_index % columns) * grid_width,
        (sprite_index // columns) * grid_height,
        image_width,
        image_height,
    )


def build_entity_image(
    source_path: Path,
    image_rect: tuple[int, int, int, int] | None,
    output_path: Path,
) -> None:
    image = Image.open(source_path).convert("RGBA")
    sprite = crop_image(image, image_rect)
    thumbnail = create_thumbnail(crop_transparent_bounds(sprite), max_size=(96, 96))
    save_lossless_webp(thumbnail, output_path)


def crop_image(image: Image.Image, image_rect: tuple[int, int, int, int] | None) -> Image.Image:
    if image_rect is None:
        return image
    x, y, width, height = image_rect
    if width <= 0 or height <= 0:
        raise ValueError("图片裁切尺寸必须为正数")
    if x < 0 or y < 0 or x + width > image.width or y + height > image.height:
        raise ValueError("图片裁切矩形超出源图边界")
    return image.crop((x, y, x + width, y + height))


def valid_image_rect(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
    )


def valid_image_size(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, int) and item > 0 for item in value)
    )


def image_error(entity: NormalizedEntity, source: str, reason: str) -> dict[str, str]:
    return {
        "source": "image",
        "source_file": entity.source_file,
        "entity_id": entity.id,
        "asset": source,
        "reason": reason,
    }


def sanitize_id(entity_id: str) -> str:
    return INVALID_FILENAME_CHARACTERS.sub("-", entity_id).replace(" ", "-")
