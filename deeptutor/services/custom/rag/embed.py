from __future__ import annotations

import hashlib
import math
from typing import Any

EMBED_DIM = 384


def _hash_feature(text: str, seed: int) -> float:
    h = hashlib.md5(f"{seed}:{text}".encode()).hexdigest()
    return (int(h[:8], 16) / 0xFFFFFFFF) * 2 - 1


def embed_text(text: str, dim: int = EMBED_DIM) -> list[float]:
    vec = [_hash_feature(text, d) for d in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def embed_batch(texts: list[str], dim: int = EMBED_DIM) -> list[list[float]]:
    return [embed_text(t, dim) for t in texts]
