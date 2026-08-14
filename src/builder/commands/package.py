from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from builder.config import (
    MANIFEST_FILENAME,
    PACKAGE_BASENAME,
    REPORTS_DIRNAME,
)
from builder.database.writer import read_artifact_metadata
from builder.models import BuildSummary
from builder.pipeline.artifact_metadata import (
    build_artifact_metadata,
    manifest_payload,
    validate_artifact_metadata,
)
from builder.pipeline.package_integrity import referenced_image_files
from builder.pipeline.release_state import validate_release_unblocked
from builder.pipeline.schema5_artifacts import validate_schema5_artifacts
from builder.pipeline.schema5_writer import validate_schema5_database_output
from builder.utils.hashing import sha256_file
from builder.utils.json_io import dump_json_file, load_json_file


def write_manifest(
    output_dir: Path,
    locale: str,
    generated_at: str,
    db_path: Path,
    summary: BuildSummary | None = None,
    game_version: str = "unknown",
    source_hash: str = "",
    artifact_metadata: dict[str, object] | None = None,
) -> Path:
    manifest_path = output_dir / MANIFEST_FILENAME
    metadata = artifact_metadata or metadata_from_summary(
        summary,
        locale,
        generated_at,
        source_hash,
        game_version,
    )
    dump_json_file(
        manifest_path,
        manifest_payload(
            metadata,
            {"file": db_path.name, "sha256": sha256_file(db_path)},
        ),
    )
    return manifest_path


def metadata_from_summary(
    summary: BuildSummary | None,
    locale: str,
    generated_at: str,
    source_hash: str,
    game_version: str,
) -> dict[str, object]:
    if summary is None:
        raise ValueError("写入 manifest 需要构建元数据")
    return build_artifact_metadata(
        summary=summary,
        locale=locale,
        generated_at=generated_at,
        source_hash=source_hash,
        game_version=game_version,
    )


def create_schema5_svdata_package(
    output_dir: Path,
    locale: str,
    generated_at: str,
    db_path: Path,
    manifest_path: Path,
    reports_dir: Path,
    conformance_path: Path,
) -> Path:
    """Package a validated schema-5 output without consulting legacy columns."""
    manifest = load_json_file(manifest_path)
    conformance = load_json_file(conformance_path)
    if not isinstance(manifest, dict) or not isinstance(conformance, dict):
        raise ValueError("schema 5 发布元数据无效")
    validate_schema5_artifacts(output_dir, manifest.get("artifacts"))
    validate_schema5_database_output(db_path, output_dir, manifest, conformance)
    package_name = PACKAGE_BASENAME.format(locale=locale.lower())
    package_path = output_dir / package_name
    entries = package_entries(
        output_dir,
        db_path,
        manifest_path,
        reports_dir,
        referenced_schema5_image_files(db_path, output_dir),
        extra_entries=[(conformance_path, conformance_path.name)],
    )
    temp_path = temporary_package_path(output_dir, package_path.stem)
    try:
        write_package_archive(temp_path, entries, zip_timestamp(generated_at))
        verify_package_archive(temp_path, entries)
        temp_path.replace(package_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return package_path


def referenced_schema5_image_files(db_path: Path, output_dir: Path) -> list[Path]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT id, relative_path, sha256 FROM visuals "
            "WHERE relative_path IS NOT NULL AND trim(relative_path) != ''"
        ).fetchall()
    finally:
        connection.close()
    files: list[Path] = []
    root = output_dir.resolve()
    for visual_id, relative_path, expected_hash in rows:
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError(f"schema 5 视觉路径无效：{visual_id}")
        path = (output_dir / relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"schema 5 视觉路径越界：{visual_id}") from exc
        if not path.is_file():
            raise ValueError(f"schema 5 视觉文件缺失：{visual_id}")
        if not isinstance(expected_hash, str) or sha256_file(path) != expected_hash:
            raise ValueError(f"schema 5 视觉文件哈希不匹配：{visual_id}")
        files.append(path)
    return sorted(set(files), key=lambda path: path.as_posix())


def create_svdata_package(
    output_dir: Path,
    locale: str,
    generated_at: str,
    db_path: Path,
    manifest_path: Path,
    reports_dir: Path,
) -> Path:
    package_name = PACKAGE_BASENAME.format(locale=locale.lower())
    package_path = output_dir / package_name
    timestamp = zip_timestamp(generated_at)
    entries = package_entries(
        output_dir,
        db_path,
        manifest_path,
        reports_dir,
        referenced_image_files(db_path, output_dir),
    )
    temp_path = temporary_package_path(output_dir, package_path.stem)
    try:
        write_package_archive(temp_path, entries, timestamp)
        verify_package_archive(temp_path, entries)
        temp_path.replace(package_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return package_path


def package_entries(
    output_dir: Path,
    db_path: Path,
    manifest_path: Path,
    reports_dir: Path,
    image_files: list[Path],
    extra_entries: list[tuple[Path, str]] | None = None,
) -> list[tuple[Path, str]]:
    resolved_output_dir = output_dir.resolve()
    reports = [
        (path, f"{REPORTS_DIRNAME}/{path.name}") for path in sorted(reports_dir.glob("*.json"))
    ]
    images = [(path, path.relative_to(resolved_output_dir).as_posix()) for path in image_files]
    return [
        (manifest_path, MANIFEST_FILENAME),
        (db_path, db_path.name),
        *reports,
        *images,
        *(extra_entries or []),
    ]


def temporary_package_path(output_dir: Path, package_stem: str) -> Path:
    with NamedTemporaryFile(
        dir=output_dir, prefix=f"{package_stem}.", suffix=".tmp", delete=False
    ) as temp:
        return Path(temp.name)


def write_package_archive(
    package_path: Path,
    entries: list[tuple[Path, str]],
    timestamp: tuple[int, int, int, int, int, int],
) -> None:
    with ZipFile(package_path, "w", compression=ZIP_DEFLATED) as archive:
        for source_path, archive_name in entries:
            add_file_to_zip(archive, source_path, archive_name, timestamp)


def verify_package_archive(package_path: Path, entries: list[tuple[Path, str]]) -> None:
    expected_names = {archive_name for _, archive_name in entries}
    with ZipFile(package_path) as archive:
        actual_names = archive.namelist()
        if archive.testzip() is not None or len(actual_names) != len(expected_names):
            raise ValueError("数据包完整性校验失败")
        if set(actual_names) != expected_names:
            raise ValueError("数据包内容不完整")


def quarantine_existing_package(output_dir: Path, locale: str) -> Path | None:
    package_path = output_dir / PACKAGE_BASENAME.format(locale=locale.lower())
    if not package_path.exists():
        return None
    quarantine_path = next_quarantine_path(package_path)
    package_path.replace(quarantine_path)
    return quarantine_path


def next_quarantine_path(package_path: Path) -> Path:
    candidate = package_path.with_name(f"{package_path.stem}.failed{package_path.suffix}")
    suffix = 1
    while candidate.exists():
        candidate = package_path.with_name(
            f"{package_path.stem}.failed-{suffix}{package_path.suffix}"
        )
        suffix += 1
    return candidate


def package_existing_output(
    output_dir: Path,
    locale: str,
) -> Path:
    manifest_path = output_dir / MANIFEST_FILENAME
    manifest = load_json_file(manifest_path) if manifest_path.is_file() else None
    if isinstance(manifest, dict) and manifest.get("schemaVersion") == 5:
        return package_existing_schema5_output(output_dir, locale, manifest)
    validate_release_unblocked(output_dir)
    if isinstance(manifest, dict) and manifest.get("schemaVersion") == 4:
        # Keep concrete integrity diagnostics observable while still refusing
        # to create an ordinary distributable from a recovery-only package.
        referenced_image_files(output_dir / "stardew.db", output_dir)
        raise ValueError("schema 4 仅可作为显式恢复资产，不能通过普通 package 发布")
    db_path = output_dir / "stardew.db"
    reports_dir = output_dir / REPORTS_DIRNAME
    metadata = validate_artifact_metadata(read_artifact_metadata(db_path), locale)
    generated_at = str(metadata["generatedAt"])
    manifest_path = write_manifest(
        output_dir=output_dir,
        locale=locale,
        generated_at=generated_at,
        db_path=db_path,
        artifact_metadata=metadata,
    )
    return create_svdata_package(
        output_dir=output_dir,
        locale=locale,
        generated_at=generated_at,
        db_path=db_path,
        manifest_path=manifest_path,
        reports_dir=reports_dir,
    )


def package_existing_schema5_output(
    output_dir: Path,
    locale: str,
    manifest: dict[str, object],
) -> Path:
    validate_release_unblocked(output_dir)
    if manifest.get("manifestVersion") != 2 or manifest.get("contentContract") != "player-facts-v1":
        raise ValueError("schema 5 manifest 契约无效")
    if manifest.get("language") != locale:
        raise ValueError("schema 5 manifest 语言与请求不一致")
    if manifest.get("publishable") is not True:
        raise ValueError("schema 5 构建不可发布")
    database = manifest.get("database")
    if not isinstance(database, dict):
        raise ValueError("schema 5 manifest 缺少 database")
    database_file = database.get("file")
    database_hash = database.get("sha256")
    if not isinstance(database_file, str) or not isinstance(database_hash, str):
        raise ValueError("schema 5 database 元数据无效")
    db_path = (output_dir / database_file).resolve()
    try:
        db_path.relative_to(output_dir.resolve())
    except ValueError as exc:
        raise ValueError("schema 5 database 路径越界") from exc
    if not db_path.is_file() or sha256_file(db_path) != database_hash:
        raise ValueError("schema 5 database 哈希不匹配")
    connection = sqlite3.connect(db_path)
    try:
        if connection.execute("PRAGMA user_version").fetchone()[0] != 5:
            raise ValueError("schema 5 database 版本无效")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("schema 5 database 完整性校验失败")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("schema 5 database 外键校验失败")
    finally:
        connection.close()
    validate_schema5_artifacts(output_dir, manifest.get("artifacts"))
    conformance_path = output_dir / "schema5-conformance.json"
    if not conformance_path.is_file():
        raise ValueError("schema 5 conformance 文件缺失")
    conformance = load_json_file(conformance_path)
    if (
        not isinstance(conformance, dict)
        or conformance.get("publishable") is not True
        or conformance.get("schemaVersion") != 5
        or conformance.get("manifestVersion") != 2
        or conformance.get("contentContract") != "player-facts-v1"
        or conformance.get("databaseSha256") != database_hash
    ):
        raise ValueError("schema 5 conformance 不可发布")
    reports_dir = output_dir / REPORTS_DIRNAME
    if not reports_dir.is_dir() or not list(reports_dir.glob("*.json")):
        raise ValueError("schema 5 reports 文件缺失")
    validate_schema5_database_output(db_path, output_dir, manifest, conformance)
    generated_at = manifest.get("generatedAt")
    if not isinstance(generated_at, str):
        raise ValueError("schema 5 manifest 缺少 generatedAt")
    return create_schema5_svdata_package(
        output_dir,
        locale,
        generated_at,
        db_path,
        output_dir / MANIFEST_FILENAME,
        output_dir / REPORTS_DIRNAME,
        conformance_path,
    )


def add_file_to_zip(
    archive: ZipFile,
    source_path: Path,
    archive_name: str,
    timestamp: tuple[int, int, int, int, int, int],
) -> None:
    info = ZipInfo(filename=archive_name, date_time=timestamp)
    info.compress_type = ZIP_DEFLATED
    archive.writestr(info, source_path.read_bytes())


def zip_timestamp(generated_at: str) -> tuple[int, int, int, int, int, int]:
    dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
