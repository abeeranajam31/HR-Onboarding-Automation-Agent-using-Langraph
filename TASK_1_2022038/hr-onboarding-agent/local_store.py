from __future__ import annotations

import json
import math
from pathlib import Path

from simple_embeddings import embed_text


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def save_index(chunks: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for chunk in chunks:
        content = chunk["content"]
        records.append(
            {
                "content": content,
                "metadata": chunk["metadata"],
                "embedding": embed_text(content),
            }
        )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f)


def load_index(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def query_index(path: Path, query: str, top_k: int = 3, metadata_filter: dict | None = None) -> list[dict]:
    records = load_index(path)
    q = embed_text(query)

    filtered = []
    for rec in records:
        meta = rec.get("metadata", {})
        if metadata_filter:
            ok = all(meta.get(k) == v for k, v in metadata_filter.items())
            if not ok:
                continue
        filtered.append(rec)

    for rec in filtered:
        rec["score"] = cosine(q, rec["embedding"])

    filtered.sort(key=lambda r: r["score"], reverse=True)
    return filtered[:top_k]
