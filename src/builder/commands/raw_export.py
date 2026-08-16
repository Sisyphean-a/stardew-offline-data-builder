from __future__ import annotations

import zipfile
from pathlib import Path

from builder.commands.build import resolve_build_inputs
from builder.utils.versions import game_version


def export_raw_data_command(
    output: Path,
    game_dir: str | None,
    unpacked_dir: str | None,
) -> None:
    """把官方解包数据（全部 JSON 与图片）打包为可离线构建的原始数据包。

    数据包内容与游戏目录的 ``Content (unpacked)`` 一致（前缀 ``Content/``）；
    任意机器解压后即可用 ``--unpacked-dir`` 全量构建，无需安装游戏。
    """
    resolved_game_dir, resolved_unpacked_dir, _ = resolve_build_inputs(
        game_dir, unpacked_dir, None, force=False
    )
    if not resolved_unpacked_dir.is_dir():
        raise FileNotFoundError(f"已解包目录不存在：{resolved_unpacked_dir}")
    version = game_version(resolved_game_dir)
    if output.suffix.lower() != ".zip":
        output = output.with_suffix(".zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for path in sorted(resolved_unpacked_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(resolved_unpacked_dir).as_posix()
            archive.write(path, f"Content/{relative}")
            total += 1
    print(f"已导出原始数据包：{output}（游戏版本 {version}，{total} 个文件）")
    print(
        f"在任意机器解压后运行：python -m builder build "
        f"--unpacked-dir \"{resolved_unpacked_dir.name}\""
    )
