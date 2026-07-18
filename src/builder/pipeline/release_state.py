from __future__ import annotations

from pathlib import Path

from builder.utils.json_io import dump_json_file, load_json_file

RELEASE_BLOCK_FILENAME = ".release-blocked.json"
FIXTURE_RELEASE_BLOCK_REASON = "fixture 构建仅供开发检查，不能打包"


def block_release(output_dir: Path, reason: str) -> None:
    if not output_dir.is_dir():
        return
    dump_json_file(
        output_dir / RELEASE_BLOCK_FILENAME,
        {"status": "blocked", "reason": reason},
    )


def clear_release_block(output_dir: Path) -> None:
    (output_dir / RELEASE_BLOCK_FILENAME).unlink(missing_ok=True)


def block_fixture_release(output_dir: Path) -> None:
    block_release(output_dir, FIXTURE_RELEASE_BLOCK_REASON)


def validate_release_unblocked(output_dir: Path) -> None:
    marker = output_dir / RELEASE_BLOCK_FILENAME
    if not marker.exists():
        return
    payload = load_json_file(marker)
    if not isinstance(payload, dict):
        raise ValueError("发布状态损坏，拒绝打包")
    if payload.get("reason") == FIXTURE_RELEASE_BLOCK_REASON:
        raise ValueError(FIXTURE_RELEASE_BLOCK_REASON)
    raise ValueError("最近一次构建未成功完成，拒绝打包")
