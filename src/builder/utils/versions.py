from __future__ import annotations

from pathlib import Path

from builder.utils.json_io import load_json_file


def game_version(game_dir: Path) -> str:
    deps_path = game_dir / "Stardew Valley.deps.json"
    if not deps_path.exists():
        return "unknown"
    payload = load_json_file(deps_path)
    if not isinstance(payload, dict):
        return "unknown"
    targets = payload.get("targets")
    if not isinstance(targets, dict):
        return "unknown"
    for target in targets.values():
        if not isinstance(target, dict):
            continue
        for name in target:
            if isinstance(name, str) and name.startswith("Stardew Valley/"):
                return name.removeprefix("Stardew Valley/")
    return "unknown"


def community_data_version(community_dir: Path | None) -> str:
    if community_dir is None:
        return "none"
    for package_path in (community_dir / "package.json", community_dir.parent / "package.json"):
        if not package_path.exists():
            continue
        payload = load_json_file(package_path)
        if isinstance(payload, dict) and isinstance(payload.get("version"), str):
            return payload["version"]
    return "unknown"
