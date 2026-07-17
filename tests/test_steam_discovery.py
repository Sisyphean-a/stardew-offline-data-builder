from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from builder.sources import steam_discovery
from builder.sources.steam_discovery import (
    discover_stardew_game_directories,
    resolve_game_directory,
)


def test_discovers_game_from_steam_root(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    game_dir = create_installed_game(steam_root)

    assert discover_stardew_game_directories([steam_root]) == [game_dir]


def test_resolves_explicit_game_directory_without_discovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "manual-game"
    game_dir.mkdir()
    monkeypatch.setattr(
        steam_discovery,
        "discover_installed_stardew_game_directories",
        lambda: pytest.fail("不应探测 Steam"),
    )

    resolved = resolve_game_directory(game_dir)

    assert resolved.path == game_dir
    assert resolved.origin == "explicit"


def test_resolves_unique_automatic_game_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = create_installed_game(tmp_path / "Steam")
    monkeypatch.setattr(
        steam_discovery,
        "discover_installed_stardew_game_directories",
        lambda: [game_dir],
    )

    resolved = resolve_game_directory(None)

    assert resolved.path == game_dir
    assert resolved.origin == "auto"


def test_automatic_resolution_reports_missing_and_ambiguous_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        steam_discovery,
        "discover_installed_stardew_game_directories",
        lambda: [],
    )

    with pytest.raises(FileNotFoundError, match="--game-dir"):
        resolve_game_directory(None)

    first = create_installed_game(tmp_path / "Steam A")
    second = create_installed_game(tmp_path / "Steam B")
    monkeypatch.setattr(
        steam_discovery,
        "discover_installed_stardew_game_directories",
        lambda: [second, first],
    )

    with pytest.raises(FileNotFoundError, match="检测到多个 Steam 游戏目录") as exc_info:
        resolve_game_directory(None)

    assert str(exc_info.value).index(str(first)) < str(exc_info.value).index(str(second))


def test_discovers_game_from_additional_steam_library(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    additional_library = tmp_path / "附加 Steam 库"
    game_dir = create_installed_game(additional_library)
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    vdf_path.parent.mkdir(parents=True)
    escaped_path = escape_keyvalues_path(additional_library)
    vdf_path.write_text(
        '"libraryfolders"\n{\n  // additional library\n  "1"\n  {\n'
        f'    "path" "{escaped_path}"\n    "apps" {{ "413150" "1" }}\n  }}\n}}',
        encoding="utf-8",
    )

    assert discover_stardew_game_directories([steam_root]) == [game_dir]


@pytest.mark.parametrize("install_dir", [".", "..", "Nested/Path", r"Nested\Path"])
def test_rejects_unsafe_manifest_install_directory(
    tmp_path: Path,
    install_dir: str,
) -> None:
    steam_root = tmp_path / "Steam"
    create_installed_game(steam_root, install_dir=install_dir)

    assert discover_stardew_game_directories([steam_root]) == []


def test_rejects_invalid_manifest_app_id_and_keyvalues(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    create_installed_game(steam_root, app_id="999")

    assert discover_stardew_game_directories([steam_root]) == []

    create_installed_game(steam_root, manifest='"AppState" { "appid" "413150"')

    assert discover_stardew_game_directories([steam_root]) == []


def test_rejects_duplicate_manifest_field_even_when_one_value_is_scalar(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    create_installed_game(
        steam_root,
        manifest=(
            '"AppState" { "appid" "413150" "appid" { "unexpected" "1" } '
            '"installdir" "Stardew Valley" }'
        ),
    )

    assert discover_stardew_game_directories([steam_root]) == []


@pytest.mark.parametrize(
    "component",
    ["steamapps", "common", "manifest", "game", "content", "dll"],
)
def test_rejects_invalid_steam_layout_component(tmp_path: Path, component: str) -> None:
    steam_root = tmp_path / "Steam"
    game_dir = create_installed_game(steam_root)
    invalidate_layout_component(steam_root, game_dir, component)

    assert discover_stardew_game_directories([steam_root]) == []


def test_rejects_relative_library_path(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    create_installed_game(tmp_path / "relative-library")
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    vdf_path.parent.mkdir(parents=True)
    vdf_path.write_text('"libraryfolders" { "1" { "path" "relative-library" } }', encoding="utf-8")

    assert discover_stardew_game_directories([steam_root]) == []


def create_installed_game(
    library_dir: Path,
    app_id: str = "413150",
    install_dir: str = "Stardew Valley",
    manifest: str | None = None,
) -> Path:
    game_dir = library_dir / "steamapps" / "common" / "Stardew Valley"
    (game_dir / "Content").mkdir(parents=True, exist_ok=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    manifest_path = library_dir / "steamapps" / "appmanifest_413150.acf"
    manifest_path.write_text(
        manifest or f'"AppState"\n{{\n  "appid" "{app_id}"\n  "installdir" "{install_dir}"\n}}',
        encoding="utf-8",
    )
    return game_dir


def escape_keyvalues_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def invalidate_layout_component(steam_root: Path, game_dir: Path, component: str) -> None:
    if component == "steamapps":
        shutil.rmtree(steam_root / "steamapps")
        (steam_root / "steamapps").write_text("", encoding="utf-8")
        return
    if component == "common":
        shutil.rmtree(steam_root / "steamapps" / "common")
        (steam_root / "steamapps" / "common").write_text("", encoding="utf-8")
        return
    if component == "manifest":
        manifest = steam_root / "steamapps" / "appmanifest_413150.acf"
        manifest.unlink()
        manifest.mkdir()
        return
    if component == "game":
        shutil.rmtree(game_dir)
        game_dir.write_text("", encoding="utf-8")
        return
    if component == "content":
        content_dir = game_dir / "Content"
        content_dir.rmdir()
        content_dir.write_text("", encoding="utf-8")
        return
    dll_path = game_dir / "Stardew Valley.dll"
    dll_path.unlink()
    dll_path.mkdir()
