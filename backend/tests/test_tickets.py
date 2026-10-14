from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.models import Ticket, TicketEvent
from tests.conftest import database_counts


def utc_date(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.utcoffset() == timedelta(0)
    return parsed


def test_empty_lists_agents_order_and_readiness_do_not_call_ai(client, agents, provider, settings):
    assert client.get("/api/tickets").json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    response = client.get("/api/agents")
    assert response.status_code == 200
    assert response.json() == agents
    assert client.get("/api/health").json() == {"status": "ok", "ai_configured": True}
    from pydantic import SecretStr

    settings.openrouter_api_key = SecretStr("")
    assert client.get("/api/health").json() == {"status": "ok", "ai_configured": False}
    assert provider.calls == []


def test_create_read_and_fresh_session_persistence(client, ticket_factory, sessions, provider):
    ticket = ticket_factory(title="  Cannot reset my password  ", description="  I need help accessing my account.  ")
    assert ticket["title"] == "Cannot reset my password"
    assert ticket["description"] == "I need help accessing my account."
    assert ticket["customer_email"] == "customer@example.com"
    assert ticket["status"] == "open"
    assert ticket["version"] == 1
    assert ticket["assignee_id"] is ticket["assignee"] is None
    assert ticket["latest_analysis"] is None
    assert ticket["analysis_stale"] is False
    UUID(ticket["id"])
    assert utc_date(ticket["updated_at"]) >= utc_date(ticket["created_at"])
    read = client.get(f"/api/tickets/{ticket['id']}")
    assert read.status_code == 200
    assert read.json() == ticket
    with sessions() as fresh:
        row = fresh.get(Ticket, UUID(ticket["id"]))
        assert (row.title, row.description, row.customer_email, row.status, row.version) == (
            ticket["title"], ticket["description"], ticket["customer_email"], "open", 1,
        )
        stored = fresh.scalars(select(TicketEvent).where(TicketEvent.ticket_id == row.id)).all()
        assert len(stored) == 1
        assert stored[0].ticket_version == 1
        assert stored[0].changes == {
            field: {"old": None, "new": ticket[field]}
            for field in ("title", "description", "customer_email", "status", "assignee_id")
        }
    assert provider.calls == []


@pytest.mark.parametrize("title_length,description_length", [(3, 10), (200, 10000)])
def test_valid_text_length_boundaries_are_persisted(client, ticket_factory, sessions, title_length, description_length):
    ticket = ticket_factory(title="x" * title_length, description="x" * description_length)
    assert len(ticket["title"]) == title_length
    assert len(ticket["description"]) == description_length
    assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    assert database_counts(sessions)["ticket_events"] == 1


def test_assignment_unassignment_status_changes_and_reopening(client, ticket_factory, agents, sessions):
    ticket = ticket_factory(assignee_id=agents[0]["id"])
    assert ticket["assignee"] == agents[0]
    changes = [
        {"status": "in_progress"},
        {"assignee_id": agents[1]["id"]},
        {"status": "resolved"},
        {"status": "open"},
        {"assignee_id": None},
        {"status": "escalated"},
        {"status": "resolved"},
    ]
    expected_changes = []
    for edit in changes:
        before = ticket
        response = client.patch(f"/api/tickets/{ticket['id']}", json={"version": ticket["version"], **edit})
        assert response.status_code == 200, response.text
        ticket = response.json()
        assert ticket["version"] == before["version"] + 1
        for field in ("title", "description", "customer_email", "status", "assignee_id"):
            assert ticket[field] == edit.get(field, before[field])
        expected_changes.append({key: {"old": before[key], "new": value} for key, value in edit.items()})
        if ticket["assignee_id"]:
            assert ticket["assignee"] == next(agent for agent in agents if agent["id"] == ticket["assignee_id"])
        else:
            assert ticket["assignee"] is None
    response = client.get(f"/api/tickets/{ticket['id']}/events")
    assert response.status_code == 200
    events = response.json()
    assert [event["ticket_version"] for event in events] == list(range(1, len(changes) + 2))
    assert [event["changes"] for event in events[1:]] == expected_changes
    assert all(event["ticket_id"] == ticket["id"] for event in events)
    assert [utc_date(event["created_at"]) for event in events] == sorted(utc_date(event["created_at"]) for event in events)
    with sessions() as fresh:
        row = fresh.get(Ticket, UUID(ticket["id"]))
        assert (row.version, row.status, row.assignee_id) == (8, "resolved", None)
        assert len(fresh.scalars(select(TicketEvent).where(TicketEvent.ticket_id == row.id)).all()) == 8


def test_multiple_changed_fields_commit_once_and_identical_edit_is_a_noop(client, ticket_factory, agents, sessions):
    original = ticket_factory()
    edit = {
        "title": "  Billing correction needed  ",
        "description": "  The same invoice was charged twice. Please check both charges.  ",
        "customer_email": "different@example.com",
        "status": "in_progress",
        "assignee_id": agents[1]["id"],
    }
    response = client.patch(f"/api/tickets/{original['id']}", json={"version": 1, **edit})
    assert response.status_code == 200
    saved = response.json()
    assert saved["version"] == 2
    assert saved["assignee"] == agents[1]
    events = client.get(f"/api/tickets/{original['id']}/events").json()
    assert len(events) == 2
    assert events[-1]["changes"] == {
        key: {"old": original[key], "new": saved[key]} for key in edit
    }
    before = database_counts(sessions)
    noop = client.patch(f"/api/tickets/{saved['id']}", json={"version": 2, **edit})
    assert noop.status_code == 200
    assert noop.json() == saved
    assert client.get(f"/api/tickets/{saved['id']}").json() == saved
    assert database_counts(sessions) == before
    assert client.get(f"/api/tickets/{saved['id']}/events").json() == events


def test_stale_patch_preserves_every_field_and_event(client, ticket_factory, agents, sessions):
    original = ticket_factory(assignee_id=agents[0]["id"])
    saved = client.patch(f"/api/tickets/{original['id']}", json={"version": 1, "status": "in_progress"}).json()
    events = client.get(f"/api/tickets/{original['id']}/events").json()
    before = database_counts(sessions)
    response = client.patch(f"/api/tickets/{original['id']}", json={
        "version": 1,
        "title": "Stale conflicting title",
        "description": "A stale client must not replace the persisted description.",
        "assignee_id": None,
        "status": "resolved",
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ticket_conflict"
    assert client.get(f"/api/tickets/{original['id']}").json() == saved
    assert client.get(f"/api/tickets/{original['id']}/events").json() == events
    assert database_counts(sessions) == before


@pytest.mark.parametrize("edit", [
    {"title": "ab"}, {"title": "x" * 201}, {"title": "   "}, {"title": None},
    {"description": "x" * 9}, {"description": "x" * 10001}, {"description": None},
    {"customer_email": "not-an-email"}, {"customer_email": None},
    {"status": "resolved"}, {"version": 1}, {"unexpected": "not allowed"},
    {"assignee_id": "not-a-uuid"},
])
def test_invalid_create_is_standard_validation_and_saves_nothing(client, sessions, edit):
    payload = {"title": "Valid ticket title", "description": "A valid ticket description.", "customer_email": "customer@example.com"}
    payload.update(edit)
    before = database_counts(sessions)
    response = client.post("/api/tickets", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert database_counts(sessions) == before


@pytest.mark.parametrize("edit", [
    {"title": None}, {"description": None}, {"customer_email": None}, {"status": None},
    {"title": "ab"}, {"title": "x" * 201}, {"description": "short"},
    {"description": "x" * 10001}, {"customer_email": "invalid"}, {"status": "closed"},
    {"assignee_id": "not-a-uuid"}, {"extra": True}, {},
])
def test_invalid_patch_leaves_ticket_and_history_untouched(client, ticket_factory, sessions, edit):
    ticket = ticket_factory()
    before = database_counts(sessions)
    events = client.get(f"/api/tickets/{ticket['id']}/events").json()
    response = client.patch(f"/api/tickets/{ticket['id']}", json={"version": 1, **edit})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    assert client.get(f"/api/tickets/{ticket['id']}/events").json() == events
    assert database_counts(sessions) == before


@pytest.mark.parametrize("version", [None, 0, -1, "1", True, 1.5])
def test_patch_requires_a_strict_positive_version(client, ticket_factory, sessions, version):
    ticket = ticket_factory()
    before = database_counts(sessions)
    payload = {"status": "in_progress"}
    if version is not None:
        payload["version"] = version
    response = client.patch(f"/api/tickets/{ticket['id']}", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    assert database_counts(sessions) == before


def test_unknown_assignee_is_a_domain_validation_error_without_partial_writes(client, ticket_factory, sessions):
    missing = str(uuid4())
    before = database_counts(sessions)
    create = client.post("/api/tickets", json={
        "title": "Unknown agent assignment", "description": "This agent does not exist in the database.",
        "customer_email": "customer@example.com", "assignee_id": missing,
    })
    assert create.status_code == 422
    assert create.json()["detail"]["code"] == "invalid_assignee"
    assert database_counts(sessions) == before
    ticket = ticket_factory()
    before = database_counts(sessions)
    patch = client.patch(f"/api/tickets/{ticket['id']}", json={"version": 1, "assignee_id": missing, "title": "Must not be committed"})
    assert patch.status_code == 422
    assert patch.json()["detail"]["code"] == "invalid_assignee"
    assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    assert database_counts(sessions) == before


def test_unknown_ticket_returns_not_found_for_all_ticket_routes(client, sessions, provider):
    missing = str(uuid4())
    before = database_counts(sessions)
    responses = [
        client.get(f"/api/tickets/{missing}"),
        client.get(f"/api/tickets/{missing}/events"),
        client.patch(f"/api/tickets/{missing}", json={"version": 1, "status": "resolved"}),
        client.post(f"/api/tickets/{missing}/analyze", json={"version": 1}),
    ]
    for response in responses:
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"
    assert database_counts(sessions) == before
    assert provider.calls == []


def test_filters_pagination_totals_and_stable_update_order(client, ticket_factory, agents, sessions):
    tickets = []
    for index in range(6):
        ticket = ticket_factory(title=f"Support ticket number {index}", assignee_id=agents[index % 2]["id"] if index < 4 else None)
        if index % 2:
            ticket = client.patch(f"/api/tickets/{ticket['id']}", json={"version": 1, "status": "in_progress"}).json()
        tickets.append(ticket)
    baseline = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dates = {ticket["id"]: baseline if index < 4 else baseline - timedelta(days=1) for index, ticket in enumerate(tickets)}
    with sessions.begin() as session:
        for ticket in tickets:
            session.get(Ticket, UUID(ticket["id"])).updated_at = dates[ticket["id"]]
    expected = sorted(tickets, key=lambda ticket: (dates[ticket["id"]], UUID(ticket["id"]).int), reverse=True)
    pages = [client.get("/api/tickets", params={"limit": 2, "offset": offset}).json() for offset in (0, 2, 4)]
    assert all((page["total"], page["limit"], page["offset"]) == (6, 2, index * 2) for index, page in enumerate(pages))
    assert [item["id"] for page in pages for item in page["items"]] == [ticket["id"] for ticket in expected]
    filters = [
        ({"status": "open"}, lambda ticket: ticket["status"] == "open"),
        ({"assignee_id": agents[0]["id"]}, lambda ticket: ticket["assignee_id"] == agents[0]["id"]),
        ({"status": "in_progress", "assignee_id": agents[1]["id"]}, lambda ticket: ticket["status"] == "in_progress" and ticket["assignee_id"] == agents[1]["id"]),
    ]
    for params, include in filters:
        response = client.get("/api/tickets", params=params)
        assert response.status_code == 200
        result = response.json()
        matching = [ticket for ticket in expected if include(ticket)]
        assert result["total"] == len(matching)
        assert [item["id"] for item in result["items"]] == [ticket["id"] for ticket in matching]
        assert all(item["latest_analysis"] is None and item["analysis_stale"] is False for item in result["items"])
    assert client.get("/api/tickets", params={"offset": 100}).json() == {"items": [], "total": 6, "limit": 20, "offset": 100}
    assert client.get("/api/tickets", params={"assignee_id": str(uuid4())}).json()["total"] == 0


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "closed"}, {"assignee_id": "not-a-uuid"},
])
def test_invalid_list_arguments_preserve_standard_validation(client, params):
    response = client.get("/api/tickets", params=params)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize("operation", ["create", "patch"])
def test_ticket_and_history_rollback_together_on_database_event_failure(client, ticket_factory, sessions, operation):
    ticket = ticket_factory() if operation == "patch" else None
    before = database_counts(sessions)
    with sessions.begin() as session:
        session.execute(text("""
            CREATE FUNCTION reject_test_ticket_event() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'private-event-error'; END; $$
        """))
        session.execute(text("""
            CREATE TRIGGER reject_test_ticket_event BEFORE INSERT ON ticket_events
            FOR EACH ROW EXECUTE FUNCTION reject_test_ticket_event()
        """))
    try:
        if operation == "create":
            response = client.post("/api/tickets", json={
                "title": "Must roll back with history", "description": "A failed history insert must roll back this ticket.",
                "customer_email": "customer@example.com",
            })
        else:
            response = client.patch(f"/api/tickets/{ticket['id']}", json={"version": 1, "title": "Must roll back this edit"})
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "internal_error"
        assert "private-event-error" not in response.text
        assert database_counts(sessions) == before
        if ticket is not None:
            assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    finally:
        with sessions.begin() as session:
            session.execute(text("DROP TRIGGER reject_test_ticket_event ON ticket_events"))
            session.execute(text("DROP FUNCTION reject_test_ticket_event()"))
