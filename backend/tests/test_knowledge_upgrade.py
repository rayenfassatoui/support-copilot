from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.models import KnowledgeChunk
from app.services.knowledge import chunk_content, retrieve
from app.tokenization import token_count
from tests.conftest import RESET_CONTENT, database_counts, unit_vector, user_payload


@pytest.mark.parametrize("content", ["word and punctuation! " * 1500, "\u754c\u00e9\U0001f680" * 2000, "A" * 18000, " leading\tspace\n" * 700 + " \n"])
def test_query_segments_preserve_every_character_under_the_native_token_limit(content):
    segments = chunk_content(content, prefix="query: ", overlap=0)
    assert "".join(segments) == content
    assert all(token_count("query: " + segment) <= 512 for segment in segments)


def test_document_overlap_preserves_coverage_and_reordered_vectors_follow_their_text(document_factory, provider, sessions):
    content = "\n".join(f"Policy section {number}: unique condition {number * 7919} requires a human review." for number in range(300))
    vectors = {}

    def reversed_batch(body, request):
        for index, value in enumerate(body["input"]):
            assert token_count(value) <= 512
            vectors[value] = unit_vector(index)
        return httpx.Response(200, json={"data": [
            {"index": index, "embedding": vectors[body["input"][index]]}
            for index in reversed(range(len(body["input"])))
        ]})

    provider.embedding_handler = reversed_batch
    document = document_factory(content=content)
    with sessions() as session:
        rows = session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.document_id == UUID(document["id"])).order_by(KnowledgeChunk.chunk_index)).all()
        previous_start, previous_end = -1, 0
        for row in rows:
            start = content.index(row.content, previous_start + 1)
            end = start + len(row.content)
            assert start <= previous_end < end
            if previous_start >= 0:
                assert start < previous_end
            assert list(row.embedding) == pytest.approx(vectors["document: " + row.content])
            previous_start, previous_end = start, end
        assert previous_end == len(content)


def test_revision_switches_retrieval_without_rewriting_old_citations(client, document_factory, ticket_factory, sessions, provider):
    original = document_factory()
    ticket = ticket_factory()
    analysis = client.post(f"/api/tickets/{ticket['id']}/analyze", json={"version": ticket["version"]}).json()
    revised_content = RESET_CONTENT.replace("30 minutes", "45 minutes")
    response = client.put(f"/api/knowledge/{original['id']}", json={"title": "Updated reset policy", "content": revised_content, "version": original["version"]})
    assert response.status_code == 200, response.text
    revised = response.json()
    assert revised["family_id"] == original["family_id"]
    assert revised["version"] == 2 and revised["id"] != original["id"]
    assert [row["id"] for row in client.get("/api/knowledge").json()] == [revised["id"]]
    old = client.get(f"/api/knowledge/{original['id']}").json()
    assert old["content"] == original["content"] and old["is_current"] is False
    assert client.get(f"/api/tickets/{ticket['id']}").json()["latest_analysis"]["citations"] == analysis["citations"]
    assert {str(item.document_id) for item in retrieve(sessions, provider.adapter, "How long is a reset link valid?")} == {revised["id"]}
    assert [row["id"] for row in client.get(f"/api/knowledge/{original['id']}/history", params={"limit": 1, "offset": 1}).json()] == [original["id"]]
    assert client.put(f"/api/knowledge/{original['id']}", json={"title": "Stale edit", "content": RESET_CONTENT, "version": 1}).status_code == 409


def test_concurrent_revisions_publish_only_one_current_version(client, document_factory, provider):
    original = document_factory()
    barrier = Barrier(2, timeout=10)

    def embed_together(body, request):
        barrier.wait()
        return httpx.Response(200, json={"data": [{"index": index, "embedding": unit_vector()} for index in range(len(body["input"]))]})

    provider.embedding_handler = embed_together
    def revise(suffix):
        return client.put(f"/api/knowledge/{original['id']}", json={"title": "Concurrent policy", "content": RESET_CONTENT + suffix, "version": 1})
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(revise, [" Revision A.", " Revision B."]))
    assert sorted(response.status_code for response in responses) == [200, 409], [response.text for response in responses]
    published = next(response.json() for response in responses if response.status_code == 200)
    assert client.get("/api/knowledge").json()[0]["id"] == published["id"]
    assert [row["version"] for row in client.get(f"/api/knowledge/{original['id']}/history").json()] == [2, 1]


def test_long_unicode_conversation_reaches_retrieval_and_chat_without_truncation(client, document_factory, ticket_factory, provider):
    document_factory()
    description = "\u754c\u00e9\U0001f680" * 1500
    ticket = ticket_factory(description=description)
    final_text = "Final customer context: please review my reset link expiry."
    assert client.post(f"/api/tickets/{ticket['id']}/messages", json={"kind": "customer", "body": final_text, "ticket_version": ticket["version"]}).status_code == 201
    current = client.get(f"/api/tickets/{ticket['id']}").json()
    response = client.post(f"/api/tickets/{ticket['id']}/analyze", json={"version": current["version"]})
    assert response.status_code == 201, response.text
    query_parts = [value for call in provider.calls_for("embeddings") for value in call.body["input"] if value.startswith("query: ")]
    assert all(token_count(value) <= 512 for value in query_parts)
    retrieval_text = "".join(value.removeprefix("query: ") for value in query_parts)
    chat_text = json.dumps(user_payload(provider.calls_for("chat/completions")[-1].body), ensure_ascii=False)
    assert description in retrieval_text and final_text in retrieval_text
    assert description in chat_text and final_text in chat_text


def test_conversation_budget_fails_before_provider_work_without_losing_messages(client, document_factory, ticket_factory, provider, sessions):
    document_factory()
    ticket = ticket_factory(description="Original request. " * 500)
    for number in range(11):
        response = client.post(f"/api/tickets/{ticket['id']}/messages", json={"kind": "customer", "body": f"Follow-up {number}: " + "x" * 9000, "ticket_version": ticket["version"]})
        assert response.status_code == 201
        ticket = client.get(f"/api/tickets/{ticket['id']}").json()
    counts, calls = database_counts(sessions), len(provider.calls)
    response = client.post(f"/api/tickets/{ticket['id']}/analyze", json={"version": ticket["version"]})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ai_input_too_long"
    assert database_counts(sessions) == counts and len(provider.calls) == calls
