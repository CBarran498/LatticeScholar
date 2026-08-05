from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Iterable, List, Sequence, Set

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "into",
    "using", "use", "based", "study", "research", "results", "method", "our", "we", "of",
    "to", "in", "on", "a", "an", "is", "by", "as", "at", "or", "be", "it", "其", "及",
    "与", "和", "的", "了", "在", "对", "通过", "研究", "方法", "结果", "本文", "一种",
}


def clean_markup(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (text or "").lower())


def stable_id(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:20]


def tokenize(text: str) -> List[str]:
    english = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{1,}", (text or "").lower())
    chinese_blocks = re.findall(r"[\u4e00-\u9fff]+", text or "")
    chinese = []
    for block in chinese_blocks:
        if len(block) == 1:
            chinese.append(block)
        else:
            chinese.extend(block[i : i + 2] for i in range(len(block) - 1))
    return [t for t in english + chinese if t not in STOPWORDS and len(t) > 1]


def keyword_set(text: str, limit: int = 40) -> Set[str]:
    counts = Counter(tokenize(text))
    return {word for word, _ in counts.most_common(limit)}


def cosine_similarity(left: str, right: str) -> float:
    a, b = Counter(tokenize(left)), Counter(tokenize(right))
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    numerator = sum(a[t] * b[t] for t in shared)
    denominator = math.sqrt(sum(v * v for v in a.values()) * sum(v * v for v in b.values()))
    return numerator / denominator if denominator else 0.0


def split_sentences(text: str) -> List[str]:
    clean = clean_markup(text)
    if not clean:
        return []
    return [s.strip() for s in re.split(r"(?<=[。！？!?\.])\s+|(?<=[。！？!?])", clean) if s.strip()]


def first_nonempty(values: Iterable[str]) -> str:
    return next((v for v in values if v), "")


def median_int(values: Sequence[int]) -> int:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return round((ordered[middle - 1] + ordered[middle]) / 2)

