from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RawEntity(BaseModel):
    source: str
    entity_type: str
    source_id: str
    internal_name: str | None
    name: str | None
    description: str | None
    locale: str | None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_file: str


class NormalizedEntity(BaseModel):
    id: str
    entity_type: str
    game_id: str | None
    internal_name: str | None
    name_zh: str
    name_en: str | None
    description_zh: str | None
    description_en: str | None
    category: str | None
    translation_status: str = "complete"
    extra_json: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    aliases: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class SearchDocument(BaseModel):
    entity_id: str
    name_zh: str
    name_en: str | None
    pinyin: str
    pinyin_initials: str
    aliases: str
    keywords: str
    search_text: str


class BuildSummary(BaseModel):
    entities: int
    missing_translations: int
    counts_by_type: dict[str, int] = Field(default_factory=dict)


class DiscoveredJsonFile(BaseModel):
    path: str
    entity_type: str
    locale: str | None
