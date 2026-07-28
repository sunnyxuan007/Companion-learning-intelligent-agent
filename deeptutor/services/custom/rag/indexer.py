from __future__ import annotations

from typing import Any

from deeptutor.services.llm import complete

from .chunker import chunk_by_paragraph, extract_structured
from .store import add_chunk, log_conflict


def ingest_document(
    source: str,
    text: str,
    doc_type: str = "",
    title: str = "",
    metadata: dict[str, Any] | None = None,
) -> list[str]:
    chunks = chunk_by_paragraph(text)
    chunk_ids: list[str] = []
    for i, chunk in enumerate(chunks):
        cid = add_chunk(
            source=source,
            content=chunk,
            chunk_id=f"{source}_{i}" if source else None,
            doc_type=doc_type,
            title=f"{title} (p{i + 1})" if title else f"{doc_type} part {i + 1}",
            metadata=metadata,
        )
        chunk_ids.append(cid)

    # Extract structured info via regex
    info = extract_structured(text)

    # LLM extraction for complex fields
    if info.get("tuition") is None and "学费" in text:
        try:
            prompt = f"从以下文本中提取学费金额，只返回数字和单位：\n\n{text[:1500]}"
            llm_result = __import__("asyncio").run(complete(prompt, system_prompt="你是一个信息提取助手。", temperature=0.1, max_tokens=50))
            if llm_result.strip():
                info["tuition_llm"] = llm_result.strip()
        except Exception:
            pass

    return chunk_ids


def extract_college_info(text: str) -> dict[str, Any]:
    info = extract_structured(text)
    return info
