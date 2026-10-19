import json

import httpx
from app.intelligence.bm25 import BM25Index, rank_order, reciprocal_rank_fusion, tokenize
from app.intelligence.embeddings import EmbeddingRetriever, cosine
from app.intelligence.retrieval import (
    rank_source_chunks_async,
    retrieve_source_context,
    retrieve_source_context_async,
    section_relevance_async,
)
from app.presentation_intelligence.small_model import bounded_batch_context_async
from app.providers.openai_compatible import OpenAICompatibleClient
from test_image_provider import mock_transport


def source(name, sections, sha="hash-a"):
    return {"name": name, "sha256": sha, "sections": sections}


CHURN_SOURCES = [source("report.md", [
    {"id": "S001", "title": "公司介绍", "text": "公司成立于上海，主营企业软件。团队覆盖研发和销售。" * 3},
    {"id": "S002", "title": "季度观察", "text": "老用户续约意愿明显下降，部分客户转向更便宜的替代产品。" * 3},
    {"id": "S003", "title": "办公环境", "text": "新办公室启用，配套会议室和培训中心。" * 3},
])]
CONCEPTS = {"churn": ("流失", "续约", "替代产品"), "office": ("办公", "会议室"), "company": ("公司", "团队")}


def concept_vector(text):
    return [float(sum(word in text for word in words)) + 0.01 for words in CONCEPTS.values()]


class FakeEmbedder:
    def __init__(self):
        self.calls = []

    async def __call__(self, texts):
        self.calls.append(list(texts))
        return [concept_vector(text) for text in texts]


def test_tokenizer_handles_chinese_bigrams_latin_words_and_numbers():
    tokens = tokenize("准确率达到89.6%，F1 提升 1,200 条")
    assert {"准确", "确率", "率达", "89.6%", "f1", "1200"} <= set(tokens)
    assert tokenize("图") == ["图"]
    assert "the" not in tokenize("the Retrieval")


def test_bm25_prefers_rare_matching_terms_and_is_deterministic():
    index = BM25Index(["背景 背景 背景", "实验 准确率 89.6%", "背景 准确率"])
    scores = index.scores("准确率 89.6%")
    assert rank_order(scores)[0] == 1
    assert scores[0] == 0
    assert index.scores("准确率 89.6%") == scores
    fused = reciprocal_rank_fusion([[1, 2], [2, 1, 0]], 3)
    assert fused[1] == fused[2] > fused[0]


def test_sync_retrieval_remains_lexical_and_reaches_late_sections():
    sections = [{"id": f"S{index:03d}", "title": "背景材料", "text": "普通背景说明。" * 40} for index in range(20)]
    sections.append({"id": "S099", "title": "收入与增长", "text": "季度收入增长 35%，续约率达到 91%。"})
    context = retrieve_source_context([source("biz.md", sections)], "收入增长", "business", "", 600)
    assert "S099" in context and "35%" in context
    assert context == retrieve_source_context([source("biz.md", sections)], "收入增长", "business", "", 600)


async def test_dense_vectors_surface_semantic_matches_bm25_misses(tmp_path):
    query = "流失预警"
    lexical, info = await rank_source_chunks_async(CHURN_SOURCES, query)
    assert info == {"strategy": "bm25", "dense": False, "chunks": 3}
    assert all(chunk["lexicalScore"] == 0 for chunk in lexical)
    assert lexical[0]["section"] != "S002"
    retriever = EmbeddingRetriever(FakeEmbedder(), "fake-model", tmp_path)
    hybrid, hybrid_info = await rank_source_chunks_async(CHURN_SOURCES, query, retriever)
    assert hybrid_info["strategy"] == "hybrid-bm25-dense-rrf" and hybrid_info["dense"]
    assert hybrid[0]["section"] == "S002"
    assert hybrid[0]["denseScore"] > 0.9
    relevance, _ = await section_relevance_async(CHURN_SOURCES, query, retriever)
    assert relevance[("report.md", "S002")] == max(relevance.values())
    async_context = await retrieve_source_context_async(
        CHURN_SOURCES, query, "business", "", limit=5000, retriever=retriever
    )
    assert "S002" in async_context


async def test_chunk_vectors_are_cached_per_source_hash(tmp_path):
    first = FakeEmbedder()
    await EmbeddingRetriever(first, "fake-model", tmp_path).similarities("客户流失", [
        {"text": "续约下降", "sourceHash": "abc"}, {"text": "办公室", "sourceHash": "abc"},
    ])
    assert len(first.calls) == 2  # query + one chunk batch
    cache_files = list(tmp_path.rglob("abc.json"))
    assert len(cache_files) == 1 and json.loads(cache_files[0].read_text())["model"] == "fake-model"
    second = FakeEmbedder()
    retriever = EmbeddingRetriever(second, "fake-model", tmp_path)
    scores = await retriever.similarities("客户流失", [
        {"text": "续约下降", "sourceHash": "abc"}, {"text": "办公室", "sourceHash": "abc"},
    ])
    assert second.calls == [["客户流失"]]
    assert retriever.cache_hits == 2 and scores[0] > scores[1]
    other_model = FakeEmbedder()
    await EmbeddingRetriever(other_model, "another-model", tmp_path).similarities(
        "x", [{"text": "续约下降", "sourceHash": "abc"}]
    )
    assert len(other_model.calls) == 2


async def test_embedding_failures_degrade_to_bm25(tmp_path):
    async def broken(_texts):
        raise RuntimeError("服务不可用")

    async def malformed(texts):
        return [[1.0]] * (len(texts) + 1)

    for embed in (broken, malformed):
        ranked, info = await rank_source_chunks_async(
            CHURN_SOURCES, "办公室", EmbeddingRetriever(embed, "m", tmp_path)
        )
        assert info["strategy"] == "bm25" and info["denseError"]
        assert ranked[0]["section"] == "S003"


async def test_async_batch_context_uses_retriever_only_without_fixed_references(tmp_path):
    embedder = FakeEmbedder()
    retriever = EmbeddingRetriever(embedder, "fake-model", tmp_path)
    fixed = await bounded_batch_context_async(
        CHURN_SOURCES, [{"purpose": "说明", "sourceRefs": [{"document": "report.md", "section": "S003"}]}],
        "t", "business", "", 2000, retriever,
    )
    assert "S003" in fixed and not embedder.calls
    open_window = await bounded_batch_context_async(
        CHURN_SOURCES, [{"purpose": "封面"}], "流失预警", "business", "", 2000, retriever
    )
    assert "S002" in open_window and embedder.calls


def test_cosine_rejects_mismatched_vectors():
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([1, 0], [1, 0, 0]) == 0


async def test_openai_compatible_embeddings_endpoint_orders_by_index(monkeypatch):
    requests = []

    def handler(request):
        requests.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]},
        ]})

    mock_transport(monkeypatch, handler)
    client = OpenAICompatibleClient("https://example.com/v1", "key", {}, 1)
    vectors = await client.embeddings("bge-m3", ["甲", "乙"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert requests == [("/v1/embeddings", {"model": "bge-m3", "input": ["甲", "乙"]})]


def test_embedding_role_builds_retriever_from_routed_model(client):
    from app.db.session import SessionLocal
    from app.intelligence.embeddings import build_embedding_retriever

    with SessionLocal() as db:
        assert build_embedding_retriever(db) is None
    provider = client.post("/api/v1/providers", json={"name": "emb", "base_url": "http://localhost:9000/v1"}).json()
    model = client.post(
        f"/api/v1/providers/{provider['id']}/models", json={"model_id": "BAAI/bge-m3", "capabilities": ["embedding"]}
    ).json()
    assert client.put("/api/v1/model-routing", json={"role": "embedding", "model_config_id": model["id"]}).status_code == 200
    with SessionLocal() as db:
        retriever = build_embedding_retriever(db)
    assert retriever is not None and retriever.model_key.endswith("BAAI/bge-m3")


def test_outline_planning_uses_routed_embedding_model(client, monkeypatch):
    from app.db.models import DeckSpecRecord
    from app.db.session import SessionLocal

    calls = []

    async def fake_embeddings(_self, model, inputs):
        calls.append((model, list(inputs)))
        return [concept_vector(text) for text in inputs]

    monkeypatch.setattr("app.providers.openai_compatible.OpenAICompatibleClient.embeddings", fake_embeddings)
    provider = client.post("/api/v1/providers", json={"name": "emb-plan", "base_url": "http://localhost:9000/v1"}).json()
    model = client.post(
        f"/api/v1/providers/{provider['id']}/models", json={"model_id": "BAAI/bge-m3", "capabilities": ["embedding"]}
    ).json()
    client.put("/api/v1/model-routing", json={"role": "embedding", "model_config_id": model["id"]})
    project = client.post("/api/v1/projects", json={"name": "向量规划"}).json()
    material = "\n".join(f"# {section['title']}\n{section['text']}" for section in CHURN_SOURCES[0]["sections"])
    client.post(f"/api/v1/projects/{project['id']}/sources", files={"file": ("report.md", material.encode(), "text/markdown")})
    response = client.post(f"/api/v1/projects/{project['id']}/outline",
                           json={"title": "流失预警", "preset": "review", "slide_count": 6})
    assert response.status_code == 200, response.text
    assert calls and all(model_id == "BAAI/bge-m3" for model_id, _ in calls)
    with SessionLocal() as db:
        ranking = db.get(DeckSpecRecord, project["id"]).reproducibility["retrieval"]["ranking"]
    assert ranking["strategy"] == "hybrid-bm25-dense-rrf" and ranking["dense"] is True
