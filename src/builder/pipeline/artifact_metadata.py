from __future__ import annotations

from collections.abc import Mapping

from builder import __version__
from builder.config import ENTITY_TYPE_LABELS, PRIMARY_ENTITY_TYPES, SCHEMA_VERSION
from builder.models import BuildSummary
from builder.pipeline.quality import quality_payload

ARTIFACT_METADATA_KEY = "artifact_metadata"


def build_artifact_metadata(
    summary: BuildSummary,
    locale: str,
    generated_at: str,
    source_hash: str = "",
    game_version: str = "unknown",
    publishable: bool = True,
) -> dict[str, object]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "builderVersion": __version__,
        "language": locale,
        "generatedAt": generated_at,
        "gameVersion": game_version,
        "sourceHash": source_hash,
        "publishable": publishable,
        "content": content_metadata(summary),
        "quality": quality_payload(summary),
    }


def content_metadata(summary: BuildSummary) -> dict[str, object]:
    return {
        "entities": summary.entities,
        "objects": summary.counts_by_type.get("object", 0),
        "crops": summary.counts_by_type.get("crop", 0),
        "fish": summary.counts_by_type.get("fish", 0),
        "villagers": summary.counts_by_type.get("villager", 0),
        "extraCounts": extra_counts(summary),
        "missingTranslations": summary.missing_translations,
        "entityTypes": entity_type_metadata(summary.counts_by_type),
    }


def extra_counts(summary: BuildSummary) -> dict[str, int]:
    return {
        entity_type: count
        for entity_type, count in sorted(summary.counts_by_type.items())
        if entity_type not in PRIMARY_ENTITY_TYPES
    }


def entity_type_metadata(counts_by_type: Mapping[str, int]) -> list[dict[str, object]]:
    return [
        {
            "id": entity_type,
            "displayName": ENTITY_TYPE_LABELS.get(entity_type),
            "count": count,
        }
        for entity_type, count in sorted(counts_by_type.items())
    ]


def validate_artifact_metadata(metadata: object, locale: str) -> dict[str, object]:
    payload = require_mapping(metadata, "构建元数据")
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("数据包元数据版本不受支持，请重新构建")
    if payload.get("language") != locale:
        raise ValueError("数据包语言与请求语言不一致")
    validate_required_strings(payload)
    content = require_mapping(payload.get("content"), "构建元数据 content")
    validate_content(content)
    quality = require_mapping(payload.get("quality"), "构建元数据 quality")
    validate_quality(quality)
    validate_publishable(payload)
    return payload


def require_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name}格式无效")
    return value


def validate_required_strings(metadata: Mapping[str, object]) -> None:
    for key in ("builderVersion", "language", "generatedAt", "gameVersion", "sourceHash"):
        if not isinstance(metadata.get(key), str):
            raise ValueError(f"构建元数据缺少 {key}")


def validate_content(content: Mapping[str, object]) -> None:
    validate_integer_fields(
        content,
        ("entities", "objects", "crops", "fish", "villagers", "missingTranslations"),
    )
    validate_extra_counts(content.get("extraCounts"))
    entity_types = content.get("entityTypes")
    if not isinstance(entity_types, list):
        raise ValueError("构建元数据缺少 entityTypes")
    for entity_type in entity_types:
        validate_entity_type(entity_type)


def validate_entity_type(entity_type: object) -> None:
    if not isinstance(entity_type, dict):
        raise ValueError("构建元数据 entityTypes 格式无效")
    if not is_nonempty_string(entity_type.get("id")):
        raise ValueError("构建元数据 entityTypes 缺少 id")
    if not is_nonempty_string(entity_type.get("displayName")):
        raise ValueError("构建元数据 entityTypes 缺少中文显示名称")
    if not isinstance(entity_type.get("count"), int):
        raise ValueError("构建元数据 entityTypes 缺少 count")


def validate_extra_counts(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("构建元数据缺少 extraCounts")
    if any(not isinstance(key, str) or not isinstance(count, int) for key, count in value.items()):
        raise ValueError("构建元数据 extraCounts 格式无效")


def validate_quality(quality: Mapping[str, object]) -> None:
    if quality.get("status") != "passed":
        raise ValueError("构建质量未通过，拒绝打包")
    translations = require_mapping(quality.get("translations"), "构建元数据 quality.translations")
    validate_integer_fields(
        translations,
        ("complete", "missing", "invalid", "notApplicable", "unusable"),
    )
    validate_integer_fields(quality, ("dataErrors",))
    validate_unlabeled_types(quality.get("unlabeledEntityTypes"))
    if quality["dataErrors"] or translations["missing"] or translations["invalid"]:
        raise ValueError("构建质量未通过，拒绝打包")


def validate_publishable(metadata: Mapping[str, object]) -> None:
    publishable = metadata.get("publishable")
    if not isinstance(publishable, bool):
        raise ValueError("构建元数据缺少 publishable")
    if not publishable:
        raise ValueError("fixture 构建仅供开发检查，不能打包")


def validate_integer_fields(mapping: Mapping[str, object], keys: tuple[str, ...]) -> None:
    if any(not isinstance(mapping.get(key), int) for key in keys):
        raise ValueError("构建元数据数值字段无效")


def validate_unlabeled_types(value: object) -> None:
    if not isinstance(value, list) or any(not is_nonempty_string(item) for item in value):
        raise ValueError("构建元数据 unlabeledEntityTypes 格式无效")
    if value:
        raise ValueError("构建质量未通过，拒绝打包")


def is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def manifest_payload(
    metadata: Mapping[str, object],
    database: Mapping[str, str],
) -> dict[str, object]:
    return {
        "format": "stardew-offline-data",
        "schemaVersion": metadata["schemaVersion"],
        "builderVersion": metadata["builderVersion"],
        "gameVersion": metadata["gameVersion"],
        "language": metadata["language"],
        "generatedAt": metadata["generatedAt"],
        "sourceHash": metadata["sourceHash"],
        "publishable": metadata["publishable"],
        "database": dict(database),
        "content": metadata["content"],
        "quality": metadata["quality"],
    }
