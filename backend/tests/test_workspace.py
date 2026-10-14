from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest

from app.auth import current_member
from app.models import Ticket
from app.schemas import MemberRead
from app.services.sla import target
from tests.conftest import chat_envelope, model_result


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_policy_changes_do_not_rewrite_existing_deadlines_and_priority_resnapshots(client, ticket_factory):
    original = ticket_factory(priority="urgent")
    created = instant(original["created_at"])
    assert instant(original["sla"]["first_response"]["due_at"]) - created == timedelta(hours=1)
    update = {"version": 1, "first_response_minutes": 120, "resolution_minutes": 300}
    response = client.patch("/api/sla-policies/urgent", json=update)
    assert response.status_code == 200 and response.json()["version"] == 2
    assert client.get(f"/api/tickets/{original['id']}").json()["sla"] == original["sla"]
    assert client.patch("/api/sla-policies/urgent", json={**update, "resolution_minutes": 999}).status_code == 409
    newer = ticket_factory(priority="urgent")
    assert instant(newer["sla"]["first_response"]["due_at"]) - instant(newer["created_at"]) == timedelta(hours=2)
    changed = client.patch(f"/api/tickets/{original['id']}", json={"version": 1, "priority": "high"}).json()
    again = client.patch(f"/api/tickets/{original['id']}", json={"version": changed["version"], "priority": "urgent"}).json()
    assert instant(again["sla"]["first_response"]["due_at"]) == created + timedelta(hours=2)
    closed = client.patch(f"/api/tickets/{original['id']}", json={"version": again["version"], "status": "resolved"}).json()
    assert closed["sla"]["resolution"]["status"] == "met"
    assert closed["sla"]["first_response"]["completed_at"] is None
    reopened = client.patch(f"/api/tickets/{original['id']}", json={"version": closed["version"], "status": "open"}).json()
    assert reopened["sla"]["resolution"]["completed_at"] is None
    assert reopened["sla"]["resolution"]["due_at"] == again["sla"]["resolution"]["due_at"]


@pytest.mark.parametrize("now_delta,completion_delta,status", [(0, None, "on_track"), (1, None, "breached"), (100, 0, "met"), (100, -1, "met"), (100, 1, "breached")])
def test_sla_boundary_uses_completion_time_not_the_current_clock(now_delta, completion_delta, status):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    completed = None if completion_delta is None else due + timedelta(seconds=completion_delta)
    assert target(due, completed, due + timedelta(seconds=now_delta)).status == status


@pytest.mark.parametrize("changes", [{"first_response_minutes": 0}, {"resolution_minutes": 525601}, {"resolution_minutes": 5}, {"first_response_minutes": True}, {"version": 0}])
def test_invalid_policy_is_not_partially_applied(client, changes):
    before = client.get("/api/sla-policies").json()
    response = client.patch("/api/sla-policies/medium", json={"version": 1, "first_response_minutes": 60, "resolution_minutes": 240, **changes})
    assert response.status_code == 422
    assert client.get("/api/sla-policies").json() == before


def test_ticket_filters_intersect_count_page_and_escape_search_metacharacters(client, ticket_factory, agents, sessions):
    first = ticket_factory(title="Refund 100% needed", priority="urgent", assignee_id=agents[0]["id"])
    second = ticket_factory(title="Refund 100 percent needed", priority="high", assignee_id=agents[1]["id"])
    third = ticket_factory(title="Refund_name issue", priority="low")
    fourth = ticket_factory(title="Folder path issue", description="The folder path is folder\\path and needs support.", priority="medium", assignee_id=agents[0]["id"])
    now = datetime.now(timezone.utc)
    with sessions.begin() as session:
        for item, minutes in [(first, -60), (second, 30), (third, 10), (fourth, 90)]:
            row = session.get(Ticket, UUID(item["id"]))
            row.created_at = now - timedelta(days=2)
            row.first_response_due_at = now + timedelta(minutes=minutes)
            row.resolution_due_at = now + timedelta(days=2)
    for query, expected in [("%", first), ("_", third), ("folder\\path", fourth)]:
        result = client.get("/api/tickets", params={"q": query}).json()
        assert result["total"] == 1 and [row["id"] for row in result["items"]] == [expected["id"]]
    result = client.get("/api/tickets", params={"assignment": "mine", "priority": "urgent", "q": "refund", "sla": "breached", "status": "open", "limit": 1}).json()
    assert result["total"] == 1 and result["items"][0]["id"] == first["id"]
    empty_page = client.get("/api/tickets", params={"assignment": "mine", "priority": "urgent", "offset": 1, "limit": 1}).json()
    assert empty_page["total"] == 1 and empty_page["items"] == []
    assert [row["id"] for row in client.get("/api/tickets", params={"assignment": "unassigned"}).json()["items"]] == [third["id"]]
    assert [row["id"] for row in client.get("/api/tickets", params={"sort": "priority"}).json()["items"]] == [first["id"], second["id"], fourth["id"], third["id"]]
    assert [row["id"] for row in client.get("/api/tickets", params={"sort": "due"}).json()["items"]] == [first["id"], third["id"], second["id"], fourth["id"]]
    assert client.get("/api/tickets", params={"assignment": "mine", "assignee_id": agents[0]["id"]}).status_code == 422


def test_completed_late_targets_are_breached_but_not_outstanding_overdue(client, ticket_factory, sessions):
    ticket = ticket_factory()
    now = datetime.now(timezone.utc)
    with sessions.begin() as session:
        row = session.get(Ticket, UUID(ticket["id"]))
        row.created_at = now - timedelta(days=3)
        row.first_response_due_at = now - timedelta(days=2)
        row.resolution_due_at = now - timedelta(days=1)
        row.first_response_at = now - timedelta(hours=12)
        row.resolved_at = now
        row.status = "resolved"
    read = client.get(f"/api/tickets/{ticket['id']}").json()
    assert read["sla"]["first_response"]["status"] == read["sla"]["resolution"]["status"] == "breached"
    assert client.get("/api/tickets", params={"sla": "breached"}).json()["total"] == 0


def test_latest_intent_filter_does_not_replace_manual_ticket_priority(client, ticket_factory, provider):
    ticket = ticket_factory(priority="low")
    provider.chat_handler = lambda body, request: httpx.Response(200, json=chat_envelope(model_result(body, intent="billing", priority="urgent")))
    assert client.post(f"/api/tickets/{ticket['id']}/analyze", json={"version": 1}).status_code == 201
    provider.chat_handler = lambda body, request: httpx.Response(200, json=chat_envelope(model_result(body, intent="technical", priority="high")))
    assert client.post(f"/api/tickets/{ticket['id']}/analyze", json={"version": 1}).status_code == 201
    assert client.get("/api/tickets", params={"intent": "billing"}).json()["total"] == 0
    result = client.get("/api/tickets", params={"intent": "technical", "priority": "low"}).json()
    assert result["total"] == 1 and result["items"][0]["id"] == ticket["id"]
    assert result["items"][0]["latest_analysis"]["priority"] == "high"


def test_saved_views_are_private_versioned_and_apply_persisted_filters(client, ticket_factory, agents, application, member):
    matching = ticket_factory(title="Refund request", priority="high", assignee_id=agents[0]["id"])
    ticket_factory(title="Refund request", priority="low", assignee_id=agents[0]["id"])
    body = {"name": "My urgent refunds", "filters": {"assignment": "mine", "priority": "high", "q": "refund", "sort": "due"}}
    created = client.post("/api/views", json=body)
    assert created.status_code == 201
    view = created.json()
    assert client.post("/api/views", json=body).status_code == 409
    restored = client.get("/api/views").json()[0]
    filtered = client.get("/api/tickets", params={key: value for key, value in restored["filters"].items() if value is not None}).json()
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == matching["id"]
    second = client.post("/api/members", json={"name": "Second agent", "email": agents[1]["email"]}).json()
    second_actor = MemberRead.model_validate(second)
    application.dependency_overrides[current_member] = lambda: second_actor
    assert client.get("/api/views").json() == []
    assert client.patch(f"/api/views/{view['id']}", json={**body, "version": 1}).status_code == 404
    assert client.delete(f"/api/views/{view['id']}", params={"version": 1}).status_code == 404
    assert client.post("/api/views", json=body).status_code == 201
    application.dependency_overrides[current_member] = lambda: member
    assert len(client.get("/api/views").json()) == 1
    updated = client.patch(f"/api/views/{view['id']}", json={"name": "My low priority refunds", "filters": {**body["filters"], "priority": "low"}, "version": 1})
    assert updated.status_code == 200 and updated.json()["version"] == 2
    assert client.patch(f"/api/views/{view['id']}", json={**body, "version": 1}).status_code == 409
    assert client.delete(f"/api/views/{view['id']}", params={"version": 1}).status_code == 409
    assert client.delete(f"/api/views/{view['id']}", params={"version": 2}).status_code == 204
    assert client.get("/api/views").json() == []


@pytest.mark.parametrize("filters", [{"offset": 20}, {"limit": 0}, {"q": "x" * 201}, {"priority": "critical"}, {"sla": "invented"}, {"unknown": True}])
def test_saved_views_cannot_store_invalid_or_unbounded_filters(client, filters):
    response = client.post("/api/views", json={"name": "Invalid view", "filters": filters})
    assert response.status_code == 422
    assert client.get("/api/views").json() == []
