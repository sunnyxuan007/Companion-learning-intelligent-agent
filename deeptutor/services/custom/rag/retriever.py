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

    # 政策/官方文档优先，FAQ/档案类靠后（官方内容权威性更高）
    def _priority(r: dict[str, Any]) -> tuple[int, int]:
        doc_type = r.get("doc_type", "")
        return (0 if doc_type == "policy" else 1, r.get("id", 0))

    for r in sorted(kw_results, key=_priority):
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
