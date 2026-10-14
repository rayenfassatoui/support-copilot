from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import re
from uuid import UUID

from fastapi import HTTPException
import pytest
from sqlalchemy import select

from app.auth import current_member
from app.models import CustomerFeedback, Ticket
from app.services.analytics import report


def prepared_survey(client, ticket_factory):
    ticket = ticket_factory()
    closed = client.patch(f"/api/tickets/{ticket['id']}", json={"version": ticket["version"], "status": "resolved"})
    assert closed.status_code == 200
    ticket = closed.json()
    response = client.post(f"/api/tickets/{ticket['id']}/feedback/request", json={"ticket_version": ticket["version"]})
    assert response.status_code == 201, response.text
    message = response.json()
    token = re.search(r"/feedback#token=([A-Za-z0-9_-]{43})", message["body"]).group(1)
    return ticket, message, token


def test_metrics_use_creation_cohorts_completed_durations_and_eligible_sla_targets(sessions, ticket_factory, member):
    now = datetime(2030, 1, 2, 12, tzinfo=timezone.utc)
    definitions = [
        (datetime(2030, 1, 1, tzinfo=timezone.utc), 30, 120),
        (datetime(2030, 1, 1, 12, tzinfo=timezone.utc), 120, 600),
        (datetime(2030, 1, 2, 10, tzinfo=timezone.utc), None, None),
        (datetime(2030, 1, 2, 11, 30, tzinfo=timezone.utc), None, None),
        (datetime(2030, 1, 3, tzinfo=timezone.utc), 10, 20),
        (datetime(2029, 12, 31, 23, 59, tzinfo=timezone.utc), 10, 20),
    ]
    tickets = [ticket_factory() for _ in definitions]
    with sessions.begin() as session:
        for item, (created, response, resolution) in zip(tickets, definitions, strict=True):
            ticket = session.get(Ticket, UUID(item["id"]))
            ticket.created_at, ticket.updated_at = created, max(now, created)
            ticket.first_response_due_at, ticket.resolution_due_at = created + timedelta(minutes=60), created + timedelta(minutes=240)
            ticket.first_response_at = created + timedelta(minutes=response) if response is not None else None
            ticket.resolved_at = created + timedelta(minutes=resolution) if resolution is not None else None
            ticket.status = "resolved" if resolution is not None else "open"
        for index, rating in enumerate((5, 2, None)):
            requested = definitions[index][0] + timedelta(hours=1)
            session.add(CustomerFeedback(ticket_id=UUID(tickets[index]["id"]), token_hash=hashlib.sha256(str(index).encode()).hexdigest(), created_by_id=member.id, created_at=requested, expires_at=requested + timedelta(days=14), rating=rating, submitted_at=requested + timedelta(minutes=5) if rating else None))
    result = report(sessions, date(2030, 1, 1), date(2030, 1, 3), now)
    assert result.tickets == 4
    assert result.first_response.model_dump() == {"completed": 2, "outstanding": 2, "average_minutes": 75.0, "sla_met": 1, "sla_breached": 2, "sla_pending": 1, "sla_percent": pytest.approx(100 / 3)}
    assert result.resolution.model_dump() == {"completed": 2, "outstanding": 2, "average_minutes": 360.0, "sla_met": 1, "sla_breached": 1, "sla_pending": 2, "sla_percent": 50.0}
    assert result.feedback.average_rating == 3.5
    assert result.feedback.satisfied_percent == 50.0
    assert result.feedback.response_percent == pytest.approx(200 / 3)
    assert [(row.day, row.tickets, row.first_response_minutes) for row in result.daily] == [(date(2030, 1, 1), 2, 75.0), (date(2030, 1, 2), 2, None)]


def test_empty_metrics_are_unknown_not_fabricated_success_and_ranges_are_bounded(client):
    response = client.get("/api/analytics", params={"start": "2030-01-01", "end": "2030-01-03"})
    assert response.status_code == 200
    body = response.json()
    assert body["tickets"] == 0
    assert body["first_response"]["average_minutes"] is None and body["first_response"]["sla_percent"] is None
    assert body["feedback"]["average_rating"] is None and body["feedback"]["response_percent"] is None
    assert [(row["day"], row["tickets"]) for row in body["daily"]] == [("2030-01-01", 0), ("2030-01-02", 0)]
    for start, end in (("2030-01-01", "2030-01-01"), ("2030-01-03", "2030-01-01"), ("2030-01-01", "2032-01-01")):
        assert client.get("/api/analytics", params={"start": start, "end": end}).status_code == 422


def test_survey_is_an_unsent_draft_and_public_submission_discloses_no_customer_identity(client, application, ticket_factory, sessions):
    ticket, message, token = prepared_survey(client, ticket_factory)
    assert message["delivery_status"] == "draft" and message["sent_at"] is None and message["approved_at"] is None
    assert client.post(f"/api/tickets/{ticket['id']}/feedback/request", json={"ticket_version": ticket["version"]}).status_code == 409
    with sessions() as session:
        survey = session.scalar(select(CustomerFeedback))
        assert survey.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert survey.message_id == UUID(message["id"])

    def unauthenticated():
        raise HTTPException(401)

    application.dependency_overrides[current_member] = unauthenticated
    valid = client.post("/api/feedback/validate", json={"token": token})
    assert valid.status_code == 200 and valid.headers["cache-control"] == "no-store"
    assert set(valid.json()) == {"expires_at"}
    submitted = client.post("/api/feedback/submit", json={"token": token, "rating": 5, "comment": " Clear and helpful. "})
    assert submitted.status_code == 200 and submitted.json() == {"submitted": True}
    assert client.post("/api/feedback/validate", json={"token": token}).status_code == 410
    assert client.post("/api/feedback/submit", json={"token": token, "rating": 1}).status_code == 410
    with sessions() as session:
        survey = session.scalar(select(CustomerFeedback))
        assert survey.rating == 5 and survey.comment == "Clear and helpful."


def test_feedback_is_single_use_under_concurrent_submissions(client, ticket_factory):
    ticket, _, token = prepared_survey(client, ticket_factory)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda rating: client.post("/api/feedback/submit", json={"token": token, "rating": rating}), [4, 5]))
    assert sorted(response.status_code for response in responses) == [200, 410]
    winner = 4 if responses[0].status_code == 200 else 5
    status = client.get(f"/api/tickets/{ticket['id']}/feedback").json()
    assert status["submitted"] is True and status["rating"] == winner and status["active"] is False


@pytest.mark.parametrize("changes", [{"rating": 0}, {"rating": 6}, {"rating": True}, {"comment": "x" * 2001}])
def test_invalid_rating_does_not_consume_the_link(client, ticket_factory, changes):
    _, _, token = prepared_survey(client, ticket_factory)
    assert client.post("/api/feedback/submit", json={"token": token, "rating": 4, **changes}).status_code == 422
    assert client.post("/api/feedback/validate", json={"token": token}).status_code == 200


def test_reopening_reclosing_and_discarding_revoke_old_links_before_replacement(client, ticket_factory):
    ticket, message, old_token = prepared_survey(client, ticket_factory)
    reopened = client.patch(f"/api/tickets/{ticket['id']}", json={"version": ticket["version"], "status": "open"}).json()
    assert client.post("/api/feedback/validate", json={"token": old_token}).status_code == 410
    closed = client.patch(f"/api/tickets/{ticket['id']}", json={"version": reopened["version"], "status": "resolved"}).json()
    assert client.post("/api/feedback/validate", json={"token": old_token}).status_code == 410
    assert client.get(f"/api/tickets/{ticket['id']}/feedback").json()["active"] is False
    deleted = client.request("DELETE", f"/api/tickets/{ticket['id']}/messages/{message['id']}", json={"version": message["version"], "ticket_version": closed["version"]})
    assert deleted.status_code == 204
    replacement = client.post(f"/api/tickets/{ticket['id']}/feedback/request", json={"ticket_version": closed["version"]})
    assert replacement.status_code == 201, replacement.text
    token = re.search(r"/feedback#token=([A-Za-z0-9_-]{43})", replacement.json()["body"]).group(1)
    assert token != old_token
    assert client.post("/api/feedback/validate", json={"token": token}).status_code == 200
    assert client.post("/api/feedback/validate", json={"token": old_token}).status_code == 410


def test_expired_survey_and_unresolved_request_are_unavailable(client, ticket_factory, sessions):
    open_ticket = ticket_factory()
    assert client.post(f"/api/tickets/{open_ticket['id']}/feedback/request", json={"ticket_version": open_ticket["version"]}).status_code == 409
    ticket, _, token = prepared_survey(client, ticket_factory)
    now = datetime.now(timezone.utc)
    with sessions.begin() as session:
        stored = session.get(Ticket, UUID(ticket["id"]))
        stored.created_at, stored.resolved_at = now - timedelta(days=16), now - timedelta(days=15, minutes=1)
        survey = session.scalar(select(CustomerFeedback).where(CustomerFeedback.ticket_id == stored.id))
        survey.created_at, survey.expires_at = now - timedelta(days=15), now - timedelta(minutes=1)
    assert client.post("/api/feedback/submit", json={"token": token, "rating": 5}).status_code == 410
    assert client.get(f"/api/tickets/{ticket['id']}/feedback").json()["active"] is False


def test_discarding_an_active_survey_draft_revokes_its_link(client, ticket_factory):
    ticket, message, token = prepared_survey(client, ticket_factory)
    assert client.post("/api/feedback/validate", json={"token": token}).status_code == 200
    response = client.request("DELETE", f"/api/tickets/{ticket['id']}/messages/{message['id']}",
                              json={"version": message["version"], "ticket_version": ticket["version"]})
    assert response.status_code == 204
    assert client.post("/api/feedback/validate", json={"token": token}).status_code == 410
    assert client.get(f"/api/tickets/{ticket['id']}/feedback").json()["active"] is False
    assert client.post(f"/api/tickets/{ticket['id']}/feedback/request", json={"ticket_version": ticket["version"]}).status_code == 201
