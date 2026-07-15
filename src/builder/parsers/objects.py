from __future__ import annotations

from pathlib import Path

from builder.models import RawEntity
from builder.parsers.localization import build_raw_entities_from_entries


def parse_objects_file(path: Path, payload: object, locale: str | None) -> list[RawEntity]:
    return build_raw_entities_from_entries(
        path,
        payload,
        locale,
        entity_type="object",
        source="official",
    )
