"""Pure-Python Okapi BM25 with Chinese-aware tokenization.

Chinese text has no word boundaries, so CJK runs are indexed as overlapping
character bigrams (a single isolated character is kept as a unigram). Latin
words and numbers are indexed as whole tokens; numbers keep their decimal part
and percent sign so that ``89.6%`` only matches the same reported value.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence

TOKEN_RE = re.compile(
    r"(?P<cjk>[㐀-鿿]+)"
    r"|(?P<number>\d+(?:[.,]\d+)*%?)"
    r"|(?P<latin>[A-Za-z][A-Za-z0-9@_+-]*)"
)
LATIN_STOP = {"the", "and", "for", "with", "this", "that", "from", "are", "was", "of", "to", "in", "on", "a", "an"}


def tokenize(text: str) -> list[str]:
    """Return BM25 tokens: CJK bigrams, latin words (lower case) and numbers."""
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(str(text or "")):
        if match.group("cjk"):
            run = match.group("cjk")
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[index:index + 2] for index in range(len(run) - 1))
        elif match.group("number"):
            tokens.append(match.group("number").replace(",", ""))
        else:
            word = match.group("latin").lower().strip("-_+")
            if len(word) >= 2 and word not in LATIN_STOP:
                tokens.append(word)
    return tokens


class BM25Index:
    """A small in-memory BM25 index; documents are token lists or raw strings."""

    def __init__(self, documents: Sequence[str | Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = [
            Counter(tokenize(document) if isinstance(document, str) else document)
            for document in documents
        ]
        self.lengths = [sum(counts.values()) for counts in self.documents]
        self.average_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        frequency: Counter = Counter()
        for counts in self.documents:
            frequency.update(counts.keys())
        total = len(self.documents)
        # BM25+ style floor keeps very common terms from turning negative.
        self.idf = {
            term: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for term, count in frequency.items()
        }

    def __len__(self) -> int:
        return len(self.documents)

    def score(self, query: str | Iterable[str], index: int) -> float:
        terms = tokenize(query) if isinstance(query, str) else list(query)
        counts = self.documents[index]
        length = self.lengths[index]
        norm = self.k1 * (1 - self.b + self.b * length / max(1e-9, self.average_length))
        total = 0.0
        for term, weight in Counter(terms).items():
            tf = counts.get(term, 0)
            if not tf:
                continue
            total += self.idf.get(term, 0.0) * weight * tf * (self.k1 + 1) / (tf + norm)
        return total

    def scores(self, query: str | Iterable[str]) -> list[float]:
        terms = tokenize(query) if isinstance(query, str) else list(query)
        return [self.score(terms, index) for index in range(len(self.documents))]


def rank_order(scores: Sequence[float]) -> list[int]:
    """Indices ordered by descending score; ties keep document order (deterministic)."""
    return sorted(range(len(scores)), key=lambda index: (-scores[index], index))


def reciprocal_rank_fusion(rankings: Sequence[Sequence[int]], size: int, k: int = 60) -> list[float]:
    """Fuse several best-first index rankings into one score per document."""
    fused = [0.0] * size
    for ranking in rankings:
        for rank, index in enumerate(ranking):
            fused[index] += 1.0 / (k + rank + 1)
    return fused
