from __future__ import annotations

from typing import Any

from .store import search_by_keywords, search_chunks


def retrieve_for_chat(message: str, college_name: str | None = None, top_k: int = 3) -> list[dict[str, Any]]:
    query = message
    if college_name:
        query = f"{college_name} {message}"

    kw_results = search_by_keywords(query, top_k=top_k * 2)
    vec_results = search_chunks(query, top_k=top_k)

    seen_titles: set[str] = set()
    merged: list[dict[str, Any]] = []

    for r in kw_results:
        t = r.get("title", "")
        if t not in seen_titles:
            seen_titles.add(t)
            r["_method"] = "keyword"
            merged.append(r)

    for r in vec_results:
        t = r.get("title", "")
        if t not in seen_titles and r.get("distance", 999) < 0.6:
            seen_titles.add(t)
            r["_method"] = "vector"
            merged.append(r)

    return merged[:top_k]


def format_context(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""
    parts: list[str] = []
    for r in results:
        title = r.get("title", "")
        content = r.get("content", "")
        source = r.get("source", "")
        parts.append(f"[{title}]({source})\n{content[:500]}")
    return "\n\n---\n\n".join(parts)
