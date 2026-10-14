from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.auth import current_member
from app.models import BusinessCalendar, Ticket
from app.services.automation import sla_alerts
from app.services.calendar import add_business_minutes


def calendar(**values):
    return BusinessCalendar(enabled=True, timezone="UTC", weekdays=[0, 1, 2, 3, 4], opens_minute=540, closes_minute=1020, holidays=[], **values)


def test_working_minutes_skip_weekends_holidays_and_closed_hours():
    schedule = calendar()
    schedule.holidays = ["2026-07-20"]
    start = datetime(2026, 7, 17, 16, 30, tzinfo=timezone.utc)
    assert add_business_minutes(start, 120, schedule) == datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)
    schedule.enabled = False
    assert add_business_minutes(start, 120, schedule) == start + timedelta(hours=2)


@pytest.mark.parametrize("start,opens,closes,minutes,expected", [
    ("2026-03-08T06:30:00+00:00", 60, 240, 90, "2026-03-08T08:00:00+00:00"),
    ("2026-03-08T06:00:00+00:00", 150, 240, 30, "2026-03-08T07:30:00+00:00"),
    ("2026-11-01T05:30:00+00:00", 60, 180, 90, "2026-11-01T07:00:00+00:00"),
    ("2026-11-01T04:00:00+00:00", 60, 90, 90, "2026-11-01T06:30:00+00:00"),
])
def test_daylight_saving_gaps_and_folds_count_real_working_minutes(start, opens, closes, minutes, expected):
    schedule = calendar()
    schedule.timezone, schedule.weekdays = "America/New_York", [6]
    schedule.opens_minute, schedule.closes_minute = opens, closes
    assert add_business_minutes(datetime.fromisoformat(start), minutes, schedule) == datetime.fromisoformat(expected)


def test_calendar_changes_are_versioned_and_do_not_rewrite_existing_targets(client, ticket_factory):
    ticket = ticket_factory()
    original = client.get("/api/automation/calendar").json()
    update = {**original, "enabled": True, "timezone": "Africa/Tunis", "weekdays": [0, 1, 2, 3, 4], "opens_minute": 540, "closes_minute": 1020, "holidays": [], "alert_minutes": 45}
    response = client.patch("/api/automation/calendar", json=update)
    assert response.status_code == 200 and response.json()["version"] == original["version"] + 1
    assert client.get(f"/api/tickets/{ticket['id']}").json()["sla"] == ticket["sla"]
    assert client.patch("/api/automation/calendar", json=update).status_code == 409
    assert client.get("/api/automation/calendar").json() == response.json()


@pytest.mark.parametrize("changes", [{"timezone": "Not/AZone"}, {"weekdays": []}, {"weekdays": [0, 0]}, {"closes_minute": 540}, {"holidays": ["2026-01-01", "2026-01-01"]}])
def test_invalid_calendar_is_not_partially_saved(client, changes):
    before = client.get("/api/automation/calendar").json()
    response = client.patch("/api/automation/calendar", json={**before, **changes})
    assert response.status_code == 422
    assert client.get("/api/automation/calendar").json() == before


def test_assignment_conditions_order_and_inactive_members_preserve_manual_ownership(client, agents, ticket_factory):
    second = client.post("/api/members", json={"name": "Second agent", "email": agents[1]["email"], "role": "agent"}).json()
    specific = client.post("/api/automation/rules", json={"name": "Urgent refunds", "position": 0, "priority": "urgent", "customer_domain": "EXAMPLE.COM", "subject_contains": "refund", "assignee_id": agents[1]["id"]}).json()
    fallback = client.post("/api/automation/rules", json={"name": "Default owner", "position": 1, "catch_all": True, "assignee_id": agents[0]["id"]}).json()
    assert ticket_factory(title="REFUND review", priority="urgent")["assignee_id"] == agents[1]["id"]
    assert ticket_factory(title="REFUND review", priority="medium")["assignee_id"] == agents[0]["id"]
    assert ticket_factory(title="REFUND review", priority="urgent", customer_email="person@other.com")["assignee_id"] == agents[0]["id"]
    assert ticket_factory(title="REFUND review", priority="urgent", assignee_id=agents[0]["id"])["assignee_id"] == agents[0]["id"]
    order = {"rules": [{"id": row["id"], "version": row["version"]} for row in (fallback, specific)]}
    reordered = client.put("/api/automation/rules/order", json=order)
    assert reordered.status_code == 200
    assert ticket_factory(title="REFUND review", priority="urgent")["assignee_id"] == agents[0]["id"]
    assert client.put("/api/automation/rules/order", json=order).status_code == 409
    assert client.get("/api/automation/rules").json() == reordered.json()
    restore = {"rules": [{"id": row["id"], "version": row["version"]} for row in reversed(reordered.json())]}
    restored = client.put("/api/automation/rules/order", json=restore).json()
    assert client.patch(f"/api/members/{second['id']}", json={"version": second["version"], "role": "agent", "active": False}).status_code == 200
    assert ticket_factory(title="REFUND review", priority="urgent")["assignee_id"] == agents[0]["id"]
    current = next(row for row in restored if row["id"] == specific["id"])
    disabled = client.patch(f"/api/automation/rules/{specific['id']}", json={key: value for key, value in {**current, "enabled": False}.items() if key != "id"})
    assert disabled.status_code == 200 and disabled.json()["enabled"] is False
    assert client.delete(f"/api/automation/rules/{specific['id']}", params={"version": current["version"]}).status_code == 409
    assert client.delete(f"/api/automation/rules/{specific['id']}", params={"version": disabled.json()["version"]}).status_code == 204


def test_rule_without_conditions_requires_explicit_catchall_and_reorder_requires_full_snapshot(client, agents):
    response = client.post("/api/automation/rules", json={"name": "Accidental catchall", "assignee_id": agents[0]["id"]})
    assert response.status_code == 422
    rule = client.post("/api/automation/rules", json={"name": "Explicit catchall", "catch_all": True, "assignee_id": agents[0]["id"]}).json()
    assert client.put("/api/automation/rules/order", json={"rules": []}).status_code == 409
    assert client.get("/api/automation/rules").json() == [rule]


def test_sla_alerts_include_boundary_and_overdue_but_exclude_completed_targets(sessions, ticket_factory):
    now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    upcoming, overdue, completed, closed, boundary = [ticket_factory() for _ in range(5)]
    with sessions.begin() as session:
        for item, due in [(upcoming, 20), (overdue, -1), (completed, -60), (closed, -60), (boundary, 30)]:
            ticket = session.get(Ticket, UUID(item["id"]))
            ticket.created_at, ticket.updated_at = now - timedelta(days=2), now
            ticket.first_response_due_at = now + timedelta(minutes=due)
            ticket.resolution_due_at = now + timedelta(days=1)
            if item == completed:
                ticket.first_response_at = now - timedelta(hours=2)
            if item == closed:
                ticket.status, ticket.resolved_at = "resolved", now
    rows = sla_alerts(sessions, now=now)["items"]
    assert [(str(row["ticket_id"]), row["target"], row["breached"]) for row in rows] == [(overdue["id"], "first_response", True), (upcoming["id"], "first_response", False), (boundary["id"], "first_response", False)]
    assert [str(row["ticket_id"]) for row in sla_alerts(sessions, limit=1, now=now)["items"]] == [overdue["id"]]


def test_agents_can_read_alerts_but_cannot_reconfigure_automation_or_mailbox(client, application, member):
    application.dependency_overrides[current_member] = lambda: member.model_copy(update={"role": "agent"})
    for path in ("/api/automation/calendar", "/api/automation/rules", "/api/mailbox"):
        assert client.get(path).status_code == 403
    assert client.post("/api/mailbox/sync").status_code == 403
    assert client.get("/api/automation/sla-alerts").status_code == 200
