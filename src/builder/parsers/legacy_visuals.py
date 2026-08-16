from __future__ import annotations

from typing import Any

MONSTER_TEXTURE_ALIASES = {
    "Frost Jelly": "Green Slime",
    # ShadowGuy can choose either runtime texture, but official Content only ships Shadow Girl.
    "Shadow Guy": "Shadow Girl",
    "Skeleton Warrior": "Skeleton",
    "Sludge": "Green Slime",
}
MONSTER_DEFAULT_FRAME_SIZE = (16, 24)
DEFAULT_VILLAGER_SPRITE_SIZE = (16, 32)
MONSTER_FRAME_SIZES = {
    "Big Slime": (32, 32),
    "Blue Squid": (24, 24),
    "Crow": (64, 64),
    "Fireball": (16, 16),
    "Frog": (16, 16),
    "Spiker": (16, 16),
    "Magma Sprite": (16, 16),
    "Magma Sparker": (16, 16),
    "Bug": (16, 16),
    "Spider": (32, 32),
    "Dwarvish Sentry": (16, 16),
    "Metal Head": (16, 16),
    "Squid Kid": (16, 16),
    "Lava Lurk": (16, 16),
    "Mummy": (16, 32),
    "Pepper Rex": (32, 32),
    "DinoMonster": (32, 32),
    "Serpent": (32, 32),
    "Royal Serpent": (32, 32),
    "Shadow Brute": (16, 32),
    "Shadow Sniper": (32, 32),
    "Shooter": (32, 32),
    "Skeleton": (16, 32),
    "Skeleton Mage": (16, 32),
}
FURNITURE_DEFAULT_SIZES = {
    "chair": (1, 2),
    "bench": (2, 2),
    "couch": (3, 2),
    "armchair": (2, 2),
    "dresser": (2, 2),
    "long table": (5, 3),
    "painting": (2, 2),
    "lamp": (1, 2),
    "bookcase": (1, 2),
    "table": (2, 3),
    "rug": (2, 3),
    "window": (3, 2),
    "fireplace": (2, 5),
    "torch": (1, 2),
    "sconce": (1, 2),
}


def apply_special_visual_metadata(
    attributes: dict[str, Any],
    entity_type: str,
    source_id: str,
    fields: list[str] | None,
) -> bool:
    if entity_type == "achievement":
        # 官方收藏页对全部成就共用同一枚光标贴图（CollectionsPage 使用
        # 标准光标 tile 25），没有按成就区分的独立图标；同一枚占位图对
        # 玩家没有辨识价值，因此标记为无官方独立视觉，由 App 用语义图标
        # 与解锁条件呈现。
        attributes["imageAvailability"] = "not_applicable"
        return True
    if entity_type == "monster":
        apply_monster_visual_metadata(attributes, source_id)
        return True
    if entity_type == "footwear":
        apply_required_sprite(attributes, "Maps/springobjects.png", int(source_id), (16, 16))
        return True
    if entity_type == "big_craftable":
        texture = attributes.get("Texture")
        source = (
            png_path(texture)
            if isinstance(texture, str) and texture
            else "TileSheets/Craftables.png"
        )
        apply_required_sprite(
            attributes,
            source,
            sprite_index(attributes.get("SpriteIndex"), source_id),
            (16, 32),
        )
        return True
    if entity_type == "furniture" and fields is not None:
        apply_furniture_sprite(attributes, source_id, fields)
        return True
    return False


def apply_monster_visual_metadata(attributes: dict[str, Any], source_id: str) -> None:
    # Monster records store gameplay fields only. Select the first AnimatedSprite
    # frame so the atlas itself is never published as the entity image.
    texture_name = MONSTER_TEXTURE_ALIASES.get(source_id, source_id)
    frame_width, frame_height = MONSTER_FRAME_SIZES.get(
        texture_name, MONSTER_DEFAULT_FRAME_SIZE
    )
    attributes.update(
        {
            "imageSource": f"Characters/Monsters/{texture_name}.png",
            "spriteIndex": 0,
            "imageGridCellSize": [frame_width, frame_height],
            "imageSize": [frame_width, frame_height],
            "imageMode": "sprite",
            "imageRequired": True,
        }
    )


def apply_required_sprite(
    attributes: dict[str, Any],
    source: str,
    sprite_index: int,
    grid_size: tuple[int, int],
    image_size: tuple[int, int] | None = None,
) -> None:
    width, height = image_size or grid_size
    attributes.update(
        {
            "imageSource": source,
            "spriteIndex": sprite_index,
            "imageGridCellSize": [*grid_size],
            "imageSize": [width, height],
            "imageMode": "sprite",
            "imageRequired": True,
        }
    )


def apply_furniture_sprite(
    attributes: dict[str, Any], source_id: str, fields: list[str]
) -> None:
    if len(fields) < 3:
        raise ValueError("家具旧格式缺少类型或尺寸字段")
    sprite_value = fields[8] if len(fields) > 8 and fields[8] else source_id
    texture_value = fields[9] if len(fields) > 9 and fields[9] else "TileSheets/furniture.png"
    width, height = furniture_size(fields[1], fields[2])
    apply_required_sprite(
        attributes,
        png_path(texture_value),
        int(sprite_value),
        (16, 16),
        (width * 16, height * 16),
    )


def furniture_size(furniture_type: str, size_field: str) -> tuple[int, int]:
    if size_field != "-1":
        parts = size_field.split()
        if len(parts) == 2 and all(part.isdigit() and int(part) > 0 for part in parts):
            return int(parts[0]), int(parts[1])
        raise ValueError(f"无效的家具尺寸：{size_field}")
    size = FURNITURE_DEFAULT_SIZES.get(furniture_type.strip().lower())
    if size is None:
        raise ValueError(f"未知的旧版家具类型：{furniture_type}")
    return size


def apply_villager_visual_metadata(
    attributes: dict[str, Any], texture: object, internal_name: str | None
) -> None:
    if is_nonvisual_villager(attributes, texture):
        attributes["imageAvailability"] = "not_applicable"
        return
    if isinstance(texture, str) and texture:
        normalized = texture.replace("\\", "/")
        texture_name = normalized.rsplit("/", maxsplit=1)[-1]
        attributes["imageSource"] = f"Portraits/{texture_name}.png"
        attributes["imageFallbackSources"] = [
            f"Characters/{normalized}.png",
            f"{normalized}.png",
        ]
    elif internal_name:
        attributes["imageSource"] = f"Portraits/{internal_name}.png"
    # Official Portraits assets are 64x64 full portraits; the walking sprite
    # fallback (16x32 or custom Size) uses imageFallbackRect instead.
    attributes["imageRect"] = [0, 0, 64, 64]
    sprite_width, sprite_height = villager_sprite_size(attributes)
    attributes["imageFallbackRect"] = [0, 0, sprite_width, sprite_height]
    attributes["imageMode"] = "portrait"
    attributes["imageRequired"] = True


def is_nonvisual_villager(attributes: dict[str, Any], texture: object) -> bool:
    return (
        not texture
        and attributes.get("SocialTab") == "HiddenAlways"
        and str(attributes.get("CanSocialize")).lower() == "false"
    )


def villager_sprite_size(attributes: dict[str, Any]) -> tuple[int, int]:
    value = attributes.get("Size")
    if isinstance(value, dict):
        width, height = value.get("X"), value.get("Y")
        if (
            type(width) is int
            and width > 0
            and type(height) is int
            and height > 0
        ):
            return width, height
    return DEFAULT_VILLAGER_SPRITE_SIZE


def sprite_index(value: object, fallback: str) -> int:
    return int(value) if isinstance(value, int) else int(fallback)


def png_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    return normalized if normalized.lower().endswith(".png") else f"{normalized}.png"
