"""将《志愿填报指南》OCR 提取的政策正文灌入 RAG 向量库。

数据源: data/user/custom/ocr_guide/policy_sections.json (阶段 A 产物)
写入: doc_meta_v2 / doc_chunks_v2 (doc_type="policy", source="广东2026志愿指南")

幂等: 先 delete_source("广东2026志愿指南") 清旧，再灌入。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deeptutor.services.custom.rag.store import add_chunk, delete_source, init_vector_store

SOURCE = "广东2026志愿指南"
DOC_TYPE = "policy"
MAX_CHUNK = 900

SECTIONS = Path(__file__).resolve().parents[1] / "data/user/custom/ocr_guide/policy_sections.json"


def split_subsections(title: str, body: str) -> list[tuple[str, str]]:
    """按 '一、二、三…' 小节切分；无小节则整段返回。"""
    if not body:
        return []
    parts: list[tuple[str, str]] = []
    # 匹配中文序号小节标题行
    pattern = re.compile(r"^([一二三四五六七八九十]+)\s*[、.．]\s*(.+)$")
    lines = body.split("\n")
    cur_title = f"{title}·概述"
    cur_body: list[str] = []
    for ln in lines:
        m = pattern.match(ln.strip())
        if m and len(ln.strip()) < 40:
            if cur_body:
                parts.append((cur_title, "\n".join(cur_body).strip()))
            cur_title = f"{title}·{m.group(2)[:30]}"
            cur_body = [ln.strip()]
        else:
            cur_body.append(ln.strip())
    if cur_body:
        parts.append((cur_title, "\n".join(cur_body).strip()))
    return parts


def chunk_text(text: str, size: int = MAX_CHUNK) -> list[str]:
    if len(text) <= size:
        return [text] if text else []
    chunks: list[str] = []
    cur = text
    while len(cur) > size:
        cut = cur.rfind("。", 0, size)
        if cut < size * 0.4:
            cut = size
        chunks.append(cur[: cut + 1].strip())
        cur = cur[cut + 1:].strip()
    if cur:
        chunks.append(cur)
    return chunks


def main() -> None:
    if not SECTIONS.exists():
        print(f"缺少 {SECTIONS}，请先运行 scripts/extract_guide_policy.py")
        sys.exit(1)

    sections = json.loads(SECTIONS.read_text(encoding="utf-8"))
    init_vector_store()

    deleted = delete_source(SOURCE)
    print(f"清理旧数据: {deleted} 条")

    total = 0
    for sec in sections:
        title = sec["title"]
        body = sec["content"]
        for sub_title, sub_body in split_subsections(title, body):
            for ci, chunk in enumerate(chunk_text(sub_body)):
                cid = add_chunk(
                    source=SOURCE,
                    content=chunk,
                    doc_type=DOC_TYPE,
                    title=f"{sub_title} [{ci + 1}]" if len(chunk_text(sub_body)) > 1 else sub_title,
                    metadata={"chapter": title, "subtitle": sub_title},
                )
                total += 1
                print(f"  + {cid} | {sub_title} | {len(chunk)}字")

    print(f"灌入完成: 共 {total} 条 policy chunk")


if __name__ == "__main__":
    main()