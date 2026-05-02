from __future__ import annotations

import math
import re
from collections import Counter

_DIMENSIONS = 256


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def embed_text(text: str) -> list[float]:
    """Deterministic offline embedding for semantic search."""
    vector = [0.0] * _DIMENSIONS
    counts = Counter(_tokenize(text))
    if not counts:
        return vector

    for token, count in counts.items():
        idx = hash(token) % _DIMENSIONS
        vector[idx] += float(count)

    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]
