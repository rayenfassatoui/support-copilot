from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event, Lock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text

from app.errors import DomainError
from app.models import KnowledgeChunk, KnowledgeDocument
from app.services.knowledge import retrieve
from app.tokenization import EMBEDDING_TOKEN_LIMIT, token_count
from tests.conftest import RESET_CONTENT, UNRELATED_CONTENT, database_counts, unit_vector


def test_documents_are_normalized_inspectable_title_ordered_and_model_owned(client, document_factory, provider, sessions):
    assert client.get("/api/knowledge").json() == []
    original = "  " + RESET_CONTENT.replace("\n", "\r\n") + "\r\n  "
    password = document_factory(title="  Password reset  ", content=original, source_url="https://example.com/policies/reset")
    billing = document_factory(title="Billing invoices", content=UNRELATED_CONTENT)
    assert password["title"] == "Password reset"
    assert password["content"] == RESET_CONTENT
    assert password["chunk_count"] == 1
    assert password["source_url"] == "https://example.com/policies/reset"
    read = client.get(f"/api/knowledge/{password['id']}")
    assert read.status_code == 200
    assert read.json() == password
    listing = client.get("/api/knowledge")
    assert listing.status_code == 200
    assert [document["id"] for document in listing.json()] == [billing["id"], password["id"]]
    assert all(set(document) == {"id", "title", "source_url", "created_at", "chunk_count"} for document in listing.json())
    with sessions() as fresh:
        document = fresh.get(KnowledgeDocument, UUID(password["id"]))
        assert document.content == RESET_CONTENT
        assert document.embedding_model == provider.settings.openrouter_embedding_model
        chunks = fresh.scalars(select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)).all()
        assert len(chunks) == 1
        assert chunks[0].content == document.content
        assert chunks[0].chunk_index == 0


def test_duplicate_normalized_content_retains_the_original_and_skips_provider(client, document_factory, provider, sessions):
    original = document_factory(source_url="https://example.com/original")
    before = database_counts(sessions)
    calls = len(provider.calls)
    duplicate = client.post("/api/knowledge", json={
        "title": "A renamed duplicate", "content": " \r\n" + RESET_CONTENT.replace("\n", "\r\n") + "\r\n ",
        "source_url": "https://example.com/replacement",
    })
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_document"
    assert len(provider.calls) == calls
    assert database_counts(sessions) == before
    assert client.get(f"/api/knowledge/{original['id']}").json() == original


def test_chunk_overlap_and_reordered_embeddings_stay_attached_to_correct_text(document_factory, provider, sessions):
    content = "A" * 850 + "B" * 850 + "C" * 200
    expected = [content[:1000], content[850:1850], content[1700:]]
    vectors = {"document: " + chunk: unit_vector(index) for index, chunk in enumerate(expected)}

    def reverse_response(body, request):
        assert len(body["input"]) == len(expected)
        return httpx.Response(200, json={"data": [
            {"index": index, "embedding": vectors[body["input"][index]]}
            for index in reversed(range(len(body["input"])))
        ]})

    provider.embedding_handler = reverse_response
    document = document_factory(content=content)
    assert document["chunk_count"] == 3
    with sessions() as fresh:
        rows = fresh.scalars(select(KnowledgeChunk).where(
            KnowledgeChunk.document_id == UUID(document["id"])
        ).order_by(KnowledgeChunk.chunk_index)).all()
        assert [row.chunk_index for row in rows] == [0, 1, 2]
        assert [row.content for row in rows] == expected
        assert rows[0].content[-150:] == rows[1].content[:150]
        assert rows[1].content[-150:] == rows[2].content[:150]
        for index, row in enumerate(rows):
            assert list(row.embedding) == pytest.approx(unit_vector(index))


def test_real_cosine_retrieval_selects_expected_source_and_breaks_ties_by_uuid(document_factory, provider, sessions):
    documents = []
    diagonal = unit_vector(0)
    diagonal[1] = 1.0
    vectors = [unit_vector(0), unit_vector(1), diagonal]
    for index, vector in enumerate(vectors):
        content = (f"AcmeCloud fictional demo policy number {index}. " + f"Source {index} documented steps. " * 3).strip()
        provider.vectors_by_text["document: " + content] = vector
        documents.append(document_factory(title=f"Policy number {index}", content=content))
    query = "The specific query used to retrieve source zero."
    provider.vectors_by_text["query: " + query] = unit_vector(0)
    result = retrieve(sessions, provider.adapter, query)
    assert [str(chunk.document_id) for chunk in result] == [documents[0]["id"], documents[2]["id"], documents[1]["id"]]
    assert result[0].text == documents[0]["content"]
    # Add enough equally distant documents to exercise both the five-source cap and UUID tie-break.
    for index in range(3, 9):
        content = (f"AcmeCloud fictional demo policy number {index}. " + "Equidistant source facts. " * 3).strip()
        provider.vectors_by_text["document: " + content] = unit_vector(0)
        documents.append(document_factory(title=f"Policy number {index}", content=content))
    with sessions() as fresh:
        nearest_ids = sorted(
            str(row.id) for row in fresh.scalars(select(KnowledgeChunk)).all()
            if str(row.document_id) in {documents[0]["id"], *(document["id"] for document in documents[3:])}
        )
    result = retrieve(sessions, provider.adapter, query)
    assert len(result) == 5
    assert [str(chunk.id) for chunk in result] == nearest_ids[:5]


INVALID_VECTORS = [
    "missing-data", "non-list-data", "incomplete", "duplicate-index", "out-of-range-index",
    "negative-index", "string-index", "boolean-index", "missing-index", "malformed-item",
    "missing-vector", "short-vector", "long-vector", "string-element", "boolean-element",
    "null-element", "nan", "infinite", "float32-overflow", "float32-underflow", "zero-vector",
]


@pytest.mark.parametrize("defect", INVALID_VECTORS)
def test_invalid_or_incomplete_vectors_never_insert_document_or_chunks(client, provider, sessions, defect):
    def malformed_response(body, request):
        data = [{"index": index, "embedding": unit_vector(index)} for index in range(len(body["input"]))]
        payload = {"data": data}
        item = data[-1]
        if defect == "missing-data":
            payload = {}
        elif defect == "non-list-data":
            payload["data"] = {"not": "a list"}
        elif defect == "incomplete":
            data.pop()
        elif defect == "duplicate-index":
            item["index"] = 0
        elif defect == "out-of-range-index":
            item["index"] = len(data)
        elif defect == "negative-index":
            item["index"] = -1
        elif defect == "string-index":
            item["index"] = str(item["index"])
        elif defect == "boolean-index":
            item["index"] = True
        elif defect == "missing-index":
            item.pop("index")
        elif defect == "malformed-item":
            data[-1] = None
        elif defect == "missing-vector":
            item.pop("embedding")
        elif defect == "short-vector":
            item["embedding"].pop()
        elif defect == "long-vector":
            item["embedding"].append(0.0)
        elif defect == "zero-vector":
            item["embedding"] = [0.0] * len(unit_vector())
        elif defect == "float32-underflow":
            item["embedding"] = [0.0] * len(unit_vector())
            item["embedding"][0] = 1e-100
        else:
            item["embedding"][0] = {
                "string-element": "1.0", "boolean-element": True, "null-element": None,
                "nan": float("nan"), "infinite": float("inf"), "float32-overflow": 1e39,
            }[defect]
        return httpx.Response(200, content=json.dumps(payload), headers={"content-type": "application/json"})

    provider.embedding_handler = malformed_response
    before = database_counts(sessions)
    response = client.post("/api/knowledge", json={"title": "Invalid vector document", "content": "A" * 850 + "B" * 850 + "C" * 200})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ai_invalid_response"
    assert database_counts(sessions) == before
    assert client.get("/api/knowledge").json() == []
    assert len(provider.calls_for("embeddings")) == 1


def test_single_embedding_allows_missing_index_but_not_a_nonzero_index(document_factory, provider, client, sessions):
    provider.embedding_handler = lambda body, request: httpx.Response(200, json={"data": [{"embedding": unit_vector()}]})
    document = document_factory()
    before = database_counts(sessions)
    provider.embedding_handler = lambda body, request: httpx.Response(200, json={"data": [{"index": 1, "embedding": unit_vector()}]})
    rejected = client.post("/api/knowledge", json={"title": "Invalid single index", "content": UNRELATED_CONTENT})
    assert rejected.status_code == 502
    assert rejected.json()["detail"]["code"] == "ai_invalid_response"
    assert database_counts(sessions) == before
    assert client.get(f"/api/knowledge/{document['id']}").json() == document


def test_embedding_batches_are_bounded_and_indices_are_batch_local(provider):
    values = [f"Embedding input number {index}" for index in range(65)]
    expected = [unit_vector(index % 7) for index in range(65)]
    provider.vectors_by_text.update(zip(values, expected))

    def reversed_batch(body, request):
        return httpx.Response(200, json={"data": [
            {"index": index, "embedding": provider.vectors_by_text[body["input"][index]]}
            for index in reversed(range(len(body["input"])))
        ]})

    provider.embedding_handler = reversed_batch
    result = provider.adapter.embed(values)
    assert result == expected
    assert [len(call.body["input"]) for call in provider.calls_for("embeddings")] == [32, 32, 1]


def test_oversized_unicode_ticket_is_rejected_before_any_provider_call(client, ticket_factory, document_factory, provider, sessions):
    document_factory()
    description = "🚀" * 4000
    ticket = ticket_factory(description=description)
    assert token_count("query: " + ticket["title"] + "\n" + description) > EMBEDDING_TOKEN_LIMIT
    before = database_counts(sessions)
    calls = len(provider.calls)
    response = client.post(f"/api/tickets/{ticket['id']}/analyze", json={"version": 1})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ai_input_too_long"
    assert len(provider.calls) == calls
    assert database_counts(sessions) == before
    assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket


def test_all_embedding_inputs_are_checked_before_first_batch(provider):
    long_text = "🚀" * 4000
    assert token_count(long_text) > EMBEDDING_TOKEN_LIMIT
    with pytest.raises(DomainError) as raised:
        provider.adapter.embed(["Valid input"] * 32 + [long_text])
    assert raised.value.code == "ai_input_too_long"
    assert provider.calls == []


def test_native_token_limit_accepts_the_boundary_and_rejects_the_next_token(provider):
    boundary = None
    for words in range(EMBEDDING_TOKEN_LIMIT + 1):
        candidate = "document: " + " a" * words
        if token_count(candidate) == EMBEDDING_TOKEN_LIMIT:
            boundary = candidate
            break
    assert boundary is not None, "Could not construct a native-token boundary input."
    assert provider.adapter.embed([boundary]) == [unit_vector()]
    above_limit = boundary + " a"
    assert token_count(above_limit) > EMBEDDING_TOKEN_LIMIT
    calls = len(provider.calls)
    with pytest.raises(DomainError) as raised:
        provider.adapter.embed([above_limit])
    assert raised.value.code == "ai_input_too_long"
    assert len(provider.calls) == calls


def test_embedding_model_mismatch_rejects_ingestion_and_retrieval_without_provider_calls(client, ticket_factory, document_factory, provider, sessions, settings):
    document = document_factory()
    ticket = ticket_factory()
    original_model = settings.openrouter_embedding_model
    settings.openrouter_embedding_model = "another/incompatible-embedding-model"
    before = database_counts(sessions)
    calls = len(provider.calls)
    responses = [
        client.post("/api/knowledge", json={"title": "Must not mix models", "content": UNRELATED_CONTENT}),
        client.post(f"/api/tickets/{ticket['id']}/analyze", json={"version": 1}),
    ]
    for response in responses:
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "embedding_model_mismatch"
    assert len(provider.calls) == calls
    assert database_counts(sessions) == before
    assert client.get(f"/api/knowledge/{document['id']}").json() == document
    settings.openrouter_embedding_model = original_model
    result = retrieve(sessions, provider.adapter, "A compatible query after restoring the model.")
    assert [str(chunk.document_id) for chunk in result] == [document["id"]]


@pytest.mark.parametrize("edit", [
    {"title": "ab"}, {"title": "x" * 201}, {"content": "x" * 49}, {"content": "x" * 20001},
    {"content": " \r\n "}, {"source_url": "javascript:alert(1)"}, {"source_url": "file:///etc/passwd"},
    {"source_url": "ftp://example.com/document"}, {"extra": "forbidden"},
])
def test_invalid_documents_use_standard_validation_and_never_call_provider(client, provider, sessions, edit):
    payload = {"title": "Valid document title", "content": RESET_CONTENT}
    payload.update(edit)
    before = database_counts(sessions)
    response = client.post("/api/knowledge", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert provider.calls == []
    assert database_counts(sessions) == before


def test_unknown_document_returns_not_found(client, provider):
    response = client.get(f"/api/knowledge/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"
    assert provider.calls == []


def test_duplicate_ingestion_race_returns_conflict_and_preserves_the_winner(client, provider, sessions):
    entered, release = Event(), Event()
    lock = Lock()
    calls = 0

    def block_first_embedding(body, request):
        nonlocal calls
        with lock:
            calls += 1
            first = calls == 1
        if first:
            entered.set()
            assert release.wait(10), "The blocked embedding call was not released."
        return httpx.Response(200, json={"data": [{"index": index, "embedding": unit_vector()} for index in range(len(body["input"]))]})

    provider.embedding_handler = block_first_embedding
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, "/api/knowledge", json={"title": "Losing concurrent document", "content": RESET_CONTENT})
        second = None
        try:
            assert entered.wait(5), "The first ingestion did not reach the provider."
            second = pool.submit(client.post, "/api/knowledge", json={"title": "Winning concurrent document", "content": RESET_CONTENT})
            winner = second.result(timeout=5)
            assert winner.status_code == 201, winner.text
        finally:
            release.set()
        loser = first.result(timeout=10)
        if second is not None:
            second.result(timeout=10)
    assert loser.status_code == 409
    assert loser.json()["detail"]["code"] == "duplicate_document"
    assert database_counts(sessions)["knowledge_documents"] == 1
    assert database_counts(sessions)["knowledge_chunks"] == 1
    assert client.get(f"/api/knowledge/{winner.json()['id']}").json() == winner.json()


def test_document_and_all_chunks_rollback_on_chunk_insert_failure(client, provider, sessions):
    before = database_counts(sessions)
    with sessions.begin() as session:
        session.execute(text("""
            CREATE FUNCTION reject_test_knowledge_chunk() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.chunk_index = 1 THEN RAISE EXCEPTION 'private-chunk-error'; END IF;
                RETURN NEW;
            END; $$
        """))
        session.execute(text("""
            CREATE TRIGGER reject_test_knowledge_chunk BEFORE INSERT ON knowledge_chunks
            FOR EACH ROW EXECUTE FUNCTION reject_test_knowledge_chunk()
        """))
    try:
        response = client.post("/api/knowledge", json={"title": "Atomic document chunks", "content": "A" * 850 + "B" * 850 + "C" * 200})
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "internal_error"
        assert "private-chunk-error" not in response.text
        assert len(provider.calls_for("embeddings")) == 1
        assert database_counts(sessions) == before
        assert client.get("/api/knowledge").json() == []
    finally:
        with sessions.begin() as session:
            session.execute(text("DROP TRIGGER reject_test_knowledge_chunk ON knowledge_chunks"))
            session.execute(text("DROP FUNCTION reject_test_knowledge_chunk()"))
