from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy


def merge_provenance(
    target: Mapping[str, object], *referenced: Mapping[str, object]
) -> dict[str, object]:
    """Copy metadata and merge source files without mutating any input mapping."""
    result = deepcopy(dict(target))
    merged: dict[str, set[str]] = {}
    for metadata in (target, *referenced):
        value = metadata.get("_provenance")
        if not isinstance(value, Mapping):
            continue
        for source, files in value.items():
            if not isinstance(files, list):
                continue
            merged.setdefault(str(source), set()).update(
                str(path) for path in files if isinstance(path, str)
            )
    if merged:
        result["_provenance"] = {
            source: sorted(files) for source, files in sorted(merged.items())
        }
    return result
