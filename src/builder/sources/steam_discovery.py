from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from builder.sources.steam_keyvalues import KeyValuesObject, KeyValuesParseError, parse_keyvalues
from builder.utils.paths import ensure_game_directory

GAME_APP_ID = "413150"
GAME_DLL_NAME = "Stardew Valley.dll"


@dataclass(frozen=True)
class ResolvedGameDirectory:
    path: Path
    origin: Literal["auto", "explicit"]


def resolve_game_directory(game_dir: Path | None) -> ResolvedGameDirectory:
    if game_dir is not None:
        return ResolvedGameDirectory(ensure_game_directory(game_dir), "explicit")
    candidates = sorted(
        set(discover_installed_stardew_game_directories()),
        key=lambda path: str(path).lower(),
    )
    if len(candidates) == 1:
        return ResolvedGameDirectory(candidates[0], "auto")
    if not candidates:
        raise FileNotFoundError(
            "未在本机 Steam 库中找到《星露谷物语》；请通过 --game-dir 指定游戏目录"
        )
    paths = "\n".join(f"- {path}" for path in candidates)
    raise FileNotFoundError(
        f"检测到多个 Steam 游戏目录：\n{paths}\n请通过 --game-dir 指定游戏目录"
    )


def discover_stardew_game_directories(steam_roots: Iterable[Path]) -> list[Path]:
    candidates = [
        game_dir
        for steam_root in steam_roots
        for library_dir in steam_library_directories(steam_root)
        if (game_dir := game_directory_from_library(library_dir)) is not None
    ]
    return sorted(set(candidates), key=lambda path: str(path).lower())


def discover_installed_stardew_game_directories() -> list[Path]:
    return discover_stardew_game_directories(default_steam_roots())


def default_steam_roots() -> list[Path]:
    if os.name != "nt":
        return []
    candidates = [*registry_steam_roots(), *program_files_steam_roots()]
    return unique_directories(candidates)


def registry_steam_roots() -> list[Path]:
    import winreg

    values = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    )
    return [path for root, key, value in values if (path := read_registry_path(root, key, value))]


def read_registry_path(root: int, key: str, value: str) -> Path | None:
    import winreg

    try:
        with winreg.OpenKey(root, key) as handle:
            raw_path, _ = winreg.QueryValueEx(handle, value)
    except OSError:
        return None
    return normalized_directory(Path(raw_path)) if isinstance(raw_path, str) else None


def program_files_steam_roots() -> list[Path]:
    names = ("ProgramFiles(x86)", "ProgramFiles")
    return [Path(value) / "Steam" for name in names if (value := os.environ.get(name))]


def steam_library_directories(steam_root: Path) -> list[Path]:
    normalized_root = normalized_directory(steam_root)
    if normalized_root is None:
        return []
    libraries = [normalized_root]
    libraries.extend(libraries_from_vdf(normalized_root))
    return unique_directories(libraries)


def libraries_from_vdf(steam_root: Path) -> list[Path]:
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.is_file():
        return []
    try:
        content = vdf_path.read_text(encoding="utf-8")
        libraryfolders = required_root_object(content, "libraryfolders")
    except (KeyValuesParseError, OSError, UnicodeError):
        return []
    return [
        directory
        for entry in libraryfolders.entries
        if isinstance(entry.value, KeyValuesObject)
        if (path := unique_direct_scalar(entry.value, "path")) is not None
        if (directory := normalized_directory(Path(path))) is not None
    ]


def game_directory_from_library(library_dir: Path) -> Path | None:
    steamapps_dir = library_dir / "steamapps"
    common_dir = steamapps_dir / "common"
    manifest_path = steamapps_dir / f"appmanifest_{GAME_APP_ID}.acf"
    if not common_dir.is_dir() or not manifest_path.is_file():
        return None
    install_dir = install_directory_from_manifest(manifest_path)
    if install_dir is None:
        return None
    resolved_common = common_dir.resolve()
    game_dir = (resolved_common / install_dir).resolve()
    if game_dir.parent != resolved_common:
        return None
    return game_dir if is_complete_game_directory(game_dir) else None


def install_directory_from_manifest(manifest_path: Path) -> str | None:
    try:
        app_state = required_root_object(manifest_path.read_text(encoding="utf-8"), "AppState")
    except (KeyValuesParseError, OSError, UnicodeError):
        return None
    app_id = unique_direct_scalar(app_state, "appid")
    install_dir = unique_direct_scalar(app_state, "installdir")
    if app_id != GAME_APP_ID or not is_safe_install_directory(install_dir):
        return None
    return install_dir


def required_root_object(text: str, expected_key: str) -> KeyValuesObject:
    document = parse_keyvalues(text)
    if len(document.entries) != 1:
        raise KeyValuesParseError("顶层对象无效")
    entry = document.entries[0]
    if entry.key != expected_key or not isinstance(entry.value, KeyValuesObject):
        raise KeyValuesParseError("顶层对象无效")
    return entry.value


def unique_direct_scalar(obj: KeyValuesObject, key: str) -> str | None:
    entries = [entry for entry in obj.entries if entry.key == key]
    if len(entries) != 1 or not isinstance(entries[0].value, str):
        return None
    return entries[0].value


def is_safe_install_directory(value: str | None) -> bool:
    if not value or value in {".", ".."} or Path(value).is_absolute():
        return False
    return "/" not in value and "\\" not in value and ".." not in Path(value).parts


def is_complete_game_directory(game_dir: Path) -> bool:
    content_dir = game_dir / "Content"
    dll_path = game_dir / GAME_DLL_NAME
    return game_dir.is_dir() and content_dir.is_dir() and dll_path.is_file()


def normalized_directory(path: Path) -> Path | None:
    if not path.is_absolute() or not path.is_dir():
        return None
    return path.resolve()


def unique_directories(paths: Iterable[Path]) -> list[Path]:
    directories = [directory for path in paths if (directory := normalized_directory(path))]
    return sorted(set(directories), key=lambda path: str(path).lower())
