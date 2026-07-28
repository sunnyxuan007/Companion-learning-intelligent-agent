from __future__ import annotations

import re
from typing import Any

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap
    return chunks


def chunk_by_paragraph(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n\n" + para if current else para
    if current:
        chunks.append(current.strip())
    return chunks


def extract_structured(text: str) -> dict[str, Any]:
    info: dict[str, Any] = {}

    # Tuition
    m = re.search(r"学费[约为：:]*?(\d[\d,.-]*)\s*元", text)
    if m:
        info["tuition"] = m.group(1)

    # Location
    m = re.search(r"(?:校区|地址)[约为：:]*?(.*?)(?:\.|。|$)", text)
    if m:
        info["campus"] = m.group(1).strip()

    # Admission ratio
    m = re.search(r"(?:录取|招生)(?:人数|计划)[约为：:]*?(\d[\d,]*)\s*(?:人|名)", text)
    if m:
        info["enrollment"] = m.group(1)

    # Scholarship
    if re.search(r"(?:奖学金|助学金)", text):
        info["has_scholarship"] = True

    # Dorm
    m = re.search(r"住宿[费条件约为：:]*?(\d[\d,.-]*)\s*元", text)
    if m:
        info["dorm_fee"] = m.group(1)

    return info
