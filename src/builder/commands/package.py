from __future__ import annotations

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
from builder.utils.hashing import sha256_file
from builder.utils.json_io import dump_json_file


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
) -> list[tuple[Path, str]]:
    resolved_output_dir = output_dir.resolve()
    reports = [
        (path, f"{REPORTS_DIRNAME}/{path.name}") for path in sorted(reports_dir.glob("*.json"))
    ]
    images = [(path, path.relative_to(resolved_output_dir).as_posix()) for path in image_files]
    return [(manifest_path, MANIFEST_FILENAME), (db_path, db_path.name), *reports, *images]


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
    validate_release_unblocked(output_dir)
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
