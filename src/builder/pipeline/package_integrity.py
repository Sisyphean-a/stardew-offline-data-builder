from __future__ import annotations

import sqlite3
from pathlib import Path

import orjson


def referenced_image_files(db_path: Path, output_dir: Path) -> list[Path]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT id, image_path, extra_json FROM entities").fetchall()
    finally:
        connection.close()
    images_dir = (output_dir / "images").resolve()
    files = [
        validate_image_file(entity_id, image_path, extra_json, output_dir, images_dir)
        for entity_id, image_path, extra_json in rows
    ]
    return sorted({path for path in files if path is not None}, key=lambda path: path.as_posix())


def validate_image_file(
    entity_id: str,
    image_path: object,
    raw_attributes: object,
    output_dir: Path,
    images_dir: Path,
) -> Path | None:
    attributes = parse_attributes(entity_id, raw_attributes)
    if image_path is None:
        if attributes.get("imageRequired") is True:
            raise ValueError(f"必需图片缺失：{entity_id}")
        return None
    if not isinstance(image_path, str) or not image_path:
        raise ValueError(f"图片路径无效：{entity_id}")
    path = (output_dir / image_path).resolve()
    try:
        path.relative_to(images_dir)
    except ValueError as exc:
        raise ValueError(f"图片路径越界：{entity_id}") from exc
    if path.suffix.lower() != ".webp" or not path.is_file():
        raise ValueError(f"图片文件缺失：{entity_id}")
    return path


def parse_attributes(entity_id: str, raw_attributes: object) -> dict[str, object]:
    try:
        attributes = orjson.loads(str(raw_attributes))
    except orjson.JSONDecodeError as exc:
        raise ValueError(f"图片元数据损坏：{entity_id}") from exc
    if not isinstance(attributes, dict):
        raise ValueError(f"图片元数据格式无效：{entity_id}")
    return attributes
