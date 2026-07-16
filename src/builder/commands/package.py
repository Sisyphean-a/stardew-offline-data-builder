from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from builder import __version__
from builder.config import (
    MANIFEST_FILENAME,
    PACKAGE_BASENAME,
    PRIMARY_ENTITY_TYPES,
    REPORTS_DIRNAME,
    SCHEMA_VERSION,
)
from builder.models import BuildSummary
from builder.utils.hashing import sha256_file
from builder.utils.json_io import dump_json_file
from builder.utils.time import current_utc_iso


def write_manifest(
    output_dir: Path,
    locale: str,
    generated_at: str,
    db_path: Path,
    summary: BuildSummary,
    game_version: str = "unknown",
) -> Path:
    manifest_path = output_dir / MANIFEST_FILENAME
    extra_counts = {
        entity_type: count
        for entity_type, count in summary.counts_by_type.items()
        if entity_type not in PRIMARY_ENTITY_TYPES
    }
    dump_json_file(
        manifest_path,
        {
            "format": "stardew-offline-data",
            "schemaVersion": SCHEMA_VERSION,
            "builderVersion": __version__,
            "gameVersion": game_version,
            "language": locale,
            "generatedAt": generated_at,
            "database": {
                "file": db_path.name,
                "sha256": sha256_file(db_path),
            },
            "content": {
                "entities": summary.entities,
                "objects": summary.counts_by_type.get("object", 0),
                "crops": summary.counts_by_type.get("crop", 0),
                "fish": summary.counts_by_type.get("fish", 0),
                "villagers": summary.counts_by_type.get("villager", 0),
                "extraCounts": extra_counts,
                "missingTranslations": summary.missing_translations,
            },
        },
    )
    return manifest_path


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
    with ZipFile(package_path, "w", compression=ZIP_DEFLATED) as archive:
        add_file_to_zip(archive, manifest_path, MANIFEST_FILENAME, timestamp)
        add_file_to_zip(archive, db_path, db_path.name, timestamp)
        for report_file in sorted(reports_dir.glob("*.json")):
            add_file_to_zip(
                archive,
                report_file,
                f"{REPORTS_DIRNAME}/{report_file.name}",
                timestamp,
            )
        images_dir = output_dir / "images"
        for image_file in sorted(images_dir.rglob("*.webp")):
            add_file_to_zip(
                archive,
                image_file,
                image_file.relative_to(output_dir).as_posix(),
                timestamp,
            )
    return package_path


def package_existing_output(
    output_dir: Path,
    locale: str,
    summary: BuildSummary,
) -> Path:
    db_path = output_dir / "stardew.db"
    reports_dir = output_dir / REPORTS_DIRNAME
    generated_at = current_utc_iso()
    manifest_path = write_manifest(
        output_dir=output_dir,
        locale=locale,
        generated_at=generated_at,
        db_path=db_path,
        summary=summary,
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
