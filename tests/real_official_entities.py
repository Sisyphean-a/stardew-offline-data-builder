from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def add_primary_objects(
    unpacked_dir: Path,
    writer: Callable[[Path, object], None],
) -> None:
    writer(
        unpacked_dir / "Data" / "Objects.json",
        {
            "24": object_data("Parsnip", "Parsnip", 0),
            "128": object_data("Pufferfish", "Pufferfish", 1),
            "472": object_data("Parsnip Seeds", "ParsnipSeeds", 0),
            "66": object_data("Amethyst", "Amethyst", 0, "Minerals"),
            "517": object_data("Glow Ring", "GlowRing", 1, "Ring"),
        },
    )


def object_data(
    name: str,
    text_key: str,
    sprite_index: int,
    item_type: str = "Basic",
) -> dict[str, object]:
    return {
        "Name": name,
        "DisplayName": f"[LocalizedText Strings\\Objects:{text_key}_Name]",
        "Description": f"[LocalizedText Strings\\Objects:{text_key}_Description]",
        "Price": 40,
        "Category": -4 if text_key == "Pufferfish" else -75,
        "Type": item_type,
        "Texture": None,
        "SpriteIndex": sprite_index,
        "ContextTags": [f"item_{text_key.lower()}"],
    }
