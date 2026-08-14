from __future__ import annotations

import hashlib
from pathlib import Path

import orjson

from builder.utils.hashing import sha256_file


def report_directory_sha256(reports_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(reports_dir.glob("*.json"), key=lambda item: item.name):
        digest.update(f"{path.name}:{sha256_file(path)}\n".encode())
    return digest.hexdigest()


def schema5_artifact_hashes(output_dir: Path) -> dict[str, str]:
    conformance = output_dir / "schema5-conformance.json"
    reports = output_dir / "reports"
    if not conformance.is_file():
        raise ValueError("schema 5 conformance 文件缺失")
    if not reports.is_dir() or not list(reports.glob("*.json")):
        raise ValueError("schema 5 reports 文件缺失")
    try:
        orjson.loads(conformance.read_bytes())
        for report in reports.glob("*.json"):
            orjson.loads(report.read_bytes())
    except orjson.JSONDecodeError as exc:
        raise ValueError("schema 5 conformance/reports JSON 无效") from exc
    return {
        "conformanceSha256": sha256_file(conformance),
        "reportsSha256": report_directory_sha256(reports),
    }


def validate_schema5_artifacts(output_dir: Path, artifacts: object) -> None:
    if not isinstance(artifacts, dict):
        raise ValueError("schema 5 manifest artifacts 无效")
    expected = schema5_artifact_hashes(output_dir)
    actual = {str(key): value for key, value in artifacts.items()}
    if actual != expected:
        raise ValueError("schema 5 manifest artifacts 哈希不一致")
