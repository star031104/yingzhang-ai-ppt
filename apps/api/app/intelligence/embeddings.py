"""Optional dense retrieval through an OpenAI-compatible ``/embeddings`` endpoint.

Dense similarity is an enhancement only: retrieval stays BM25-based whenever no
embedding model is routed, the provider fails, or vectors are malformed. Chunk
vectors are cached on disk per (model, source content hash) so that re-planning
the same materials does not re-embed them.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

EmbedFunction = Callable[[list[str]], Awaitable[list[list[float]]]]
MAX_EMBED_CHARACTERS = 2000
BATCH_SIZE = 32


def text_hash(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def _valid_vector(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item)
        for item in value
    )


class EmbeddingRetriever:
    """Embeds chunk texts with a disk cache and scores them against a query."""

    def __init__(self, embed: EmbedFunction, model_key: str, cache_dir: Path | None = None):
        self.embed = embed
        self.model_key = model_key
        self.cache_dir = (Path(cache_dir) / text_hash(model_key)[:24]) if cache_dir else None
        self.requests = 0
        self.cache_hits = 0

    def _cache_path(self, source_hash: str) -> Path | None:
        if not self.cache_dir:
            return None
        safe = "".join(ch for ch in source_hash if ch.isalnum())[:64] or "unknown"
        return self.cache_dir / f"{safe}.json"

    def _load(self, source_hash: str) -> dict[str, list[float]]:
        path = self._cache_path(source_hash)
        if not path or not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict) or data.get("model") != self.model_key:
            return {}
        vectors = data.get("vectors")
        return {key: value for key, value in vectors.items() if _valid_vector(value)} if isinstance(vectors, dict) else {}

    def _store(self, source_hash: str, vectors: dict[str, list[float]]) -> None:
        path = self._cache_path(source_hash)
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps({"model": self.model_key, "vectors": vectors}), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            # The cache is an optimisation; a read-only disk must not break planning.
            pass

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), BATCH_SIZE):
            batch = [text[:MAX_EMBED_CHARACTERS] for text in texts[offset:offset + BATCH_SIZE]]
            self.requests += 1
            result = await self.embed(batch)
            if not isinstance(result, list) or len(result) != len(batch) or not all(map(_valid_vector, result)):
                raise ValueError("向量模型返回的结果数量或格式无效")
            vectors.extend([float(item) for item in vector] for vector in result)
        return vectors

    async def chunk_vectors(self, chunks: list[dict]) -> list[list[float]]:
        """Return one vector per chunk, grouped by the chunk's ``sourceHash`` for caching."""
        by_source: dict[str, list[int]] = {}
        for index, chunk in enumerate(chunks):
            by_source.setdefault(str(chunk.get("sourceHash") or chunk.get("document") or ""), []).append(index)
        result: list[list[float] | None] = [None] * len(chunks)
        for source_hash, indices in by_source.items():
            cached = self._load(source_hash)
            missing = []
            for index in indices:
                key = text_hash(chunks[index]["text"])
                if key in cached:
                    result[index] = cached[key]
                    self.cache_hits += 1
                else:
                    missing.append(index)
            if missing:
                unique = list(dict.fromkeys(chunks[index]["text"] for index in missing))
                fresh = dict(zip(map(text_hash, unique), await self._embed_texts(unique), strict=True))
                for index in missing:
                    result[index] = fresh[text_hash(chunks[index]["text"])]
                cached.update(fresh)
                self._store(source_hash, cached)
        return [vector or [] for vector in result]

    async def similarities(self, query: str, chunks: list[dict]) -> list[float]:
        if not chunks:
            return []
        query_vector = (await self._embed_texts([query]))[0]
        return [cosine(query_vector, vector) for vector in await self.chunk_vectors(chunks)]


def build_embedding_retriever(db) -> EmbeddingRetriever | None:
    """Create a retriever from the routed ``embedding`` model, or ``None`` when unavailable."""
    from app.config import settings
    from app.db.models import ModelConfig, Provider, RoleAssignment
    from app.providers.openai_compatible import OpenAICompatibleClient
    from app.security.secrets import secret_store

    assignment = db.get(RoleAssignment, "embedding")
    if not assignment:
        return None
    model = db.get(ModelConfig, assignment.model_config_id)
    provider = db.get(Provider, model.provider_id) if model else None
    if not model or not provider or not provider.enabled:
        return None
    client = OpenAICompatibleClient(
        provider.base_url,
        secret_store.get(provider.api_key_ref),
        provider.extra_headers,
        settings.request_timeout_seconds,
    )

    async def embed(texts: list[str]) -> list[list[float]]:
        return await client.embeddings(model.model_id, texts)

    return EmbeddingRetriever(
        embed,
        f"{provider.base_url.rstrip('/')}|{model.model_id}",
        settings.artifact_root / ".cache" / "embeddings",
    )
