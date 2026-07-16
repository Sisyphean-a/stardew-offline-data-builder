from __future__ import annotations


def resolve_bundle_area_name(
    value: str,
    source_locale: str | None,
    locale: str,
    tables: dict[str, dict[str, dict[str, str]]],
) -> str | None:
    if source_locale != "en":
        return None
    english = tables.get("en", {}).get("strings/locations", {})
    target = tables.get(locale, {}).get("strings/locations", {})
    for key, english_value in english.items():
        if english_value == value:
            return target.get(key)
    return None
