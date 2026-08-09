from __future__ import annotations

from copy import deepcopy

from builder.models import NormalizedEntity
from builder.pipeline.normalize_support import item_key_value
from builder.pipeline.provenance import merge_provenance

IMAGE_METADATA_KEYS = (
    "imageSource",
    "imageFallbackSources",
    "imageRect",
    "spriteIndex",
    "imageGridCellSize",
    "imageSize",
    "imageMode",
    "imageRequired",
    "imageAvailability",
)
AVATAR_METADATA_KEYS = ("imageSource", "imageRect", "imageMode", "imageFallbackSources")


def inherit_harvest_item_image(
    entity: NormalizedEntity, items: dict[str, NormalizedEntity]
) -> NormalizedEntity:
    harvest_id = entity.extra_json.get("HarvestItemId") or entity.game_id
    item = items.get(item_key_value(harvest_id))
    if item is None:
        return entity
    extra_json = merge_provenance(entity.extra_json, item.extra_json)
    for key in IMAGE_METADATA_KEYS:
        if key in item.extra_json:
            extra_json[key] = deepcopy(item.extra_json[key])
    return entity.model_copy(update={"extra_json": extra_json})


def copy_avatar_metadata(
    target: dict[str, object], villager: dict[str, object]
) -> dict[str, object]:
    result = merge_provenance(target, villager)
    for key in AVATAR_METADATA_KEYS:
        if key in villager:
            result[key] = deepcopy(villager[key])
    if any(key in result for key in ("imageSource", "imageRect", "imageMode")):
        result["imageRequired"] = False
    return result
