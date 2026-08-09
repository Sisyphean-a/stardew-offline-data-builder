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
