from __future__ import annotations

from typing import Any

from builder.parsers.legacy_visuals import (
    apply_special_visual_metadata,
    apply_villager_visual_metadata,
)


def apply_image_metadata(
    attributes: dict[str, Any],
    entity_type: str,
    internal_name: str | None,
    source_id: str,
    fields: list[str] | None = None,
) -> None:
    texture = attributes.get("Texture") or attributes.get("TextureName")
    if entity_type == "tool":
        apply_tool_visual_metadata(attributes, texture)
        return
    if entity_type == "villager":
        apply_villager_visual_metadata(attributes, texture, internal_name)
    elif entity_type == "crop":
        apply_crop_visual_metadata(attributes)
    elif apply_special_visual_metadata(attributes, entity_type, source_id, fields):
        return
    elif isinstance(texture, str) and texture:
        attributes["imageSource"] = texture.replace("\\", "/") + ".png"
    elif entity_type == "object":
        attributes["imageSource"] = "Maps/springobjects.png"
    if isinstance(attributes.get("SpriteIndex"), int):
        attributes["spriteIndex"] = attributes["SpriteIndex"]
        if entity_type == "object":
            attributes.update(
                {
                    "imageGridCellSize": [16, 16],
                    "imageSize": [16, 16],
                    "imageMode": "sprite",
                }
            )


def apply_crop_visual_metadata(attributes: dict[str, Any]) -> None:
    """作物贴图布局：每株作物占用 16x32 单元格，SpriteIndex 是行号。

    crops.png 的单元格并非普通 16x16 网格：SpriteIndex 为偶数时作物占据
    x∈[0,112] 的 16x32 区域，为奇数时整体右移 128px（第二列）。成熟植株
    的相位下标：可再收作物固定为 6（dayOfCurrentPhase<=0），一次性作物为
    DaysInPhase 数量 + 1（对应游戏 getSourceRect 的 currentPhase+1）。
    """
    texture = attributes.get("Texture") or attributes.get("TextureName")
    sprite_index = attributes.get("SpriteIndex")
    days = attributes.get("DaysInPhase")
    regrow = attributes.get("RegrowDays")
    if (
        not isinstance(texture, str)
        or not texture
        or not isinstance(sprite_index, int)
        or sprite_index < 0
        or not isinstance(days, list)
        or not days
    ):
        return
    phase_index = 6 if (isinstance(regrow, int) and regrow > 0) else len(days) + 1
    x = phase_index * 16 + (128 if sprite_index % 2 else 0)
    y = (sprite_index // 2) * 32
    attributes["imageSource"] = texture.replace("\\", "/") + ".png"
    attributes["imageRect"] = [x, y, 16, 32]


def apply_tool_visual_metadata(attributes: dict[str, Any], texture: object) -> None:
    menu_index = attributes.get("MenuSpriteIndex")
    if not isinstance(menu_index, int) or menu_index < 0:
        menu_index = attributes.get("SpriteIndex")
    if not isinstance(menu_index, int) or menu_index < 0:
        return
    if isinstance(texture, str) and texture:
        attributes["imageSource"] = texture.replace("\\", "/") + ".png"
    attributes.update(
        {
            "spriteIndex": menu_index,
            "imageGridCellSize": [16, 16],
            "imageSize": [16, 16],
            "imageMode": "sprite",
        }
    )
