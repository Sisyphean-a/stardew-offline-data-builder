from __future__ import annotations

from pypinyin import lazy_pinyin

from builder.models import NormalizedEntity, SearchDocument


def build_search_documents(entities: list[NormalizedEntity]) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    for entity in entities:
        pinyin_tokens = lazy_pinyin(entity.name_zh)
        pinyin = " ".join(pinyin_tokens)
        initials = "".join(token[0] for token in pinyin_tokens if token)
        alias_text = " ".join(entity.aliases)
        keyword_text = " ".join(entity.keywords)
        parts = [entity.name_zh, entity.name_en or "", pinyin, initials, alias_text, keyword_text]
        documents.append(
            SearchDocument(
                entity_id=entity.id,
                name_zh=entity.name_zh,
                name_en=entity.name_en,
                pinyin=pinyin,
                pinyin_initials=initials,
                aliases=alias_text,
                keywords=keyword_text,
                search_text=" ".join(part for part in parts if part).strip(),
            )
        )
    return documents
