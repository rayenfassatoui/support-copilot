from concurrent.futures import ThreadPoolExecutor
import json
import smtplib
from threading import Event

import pytest

from app.integrations.mail import SMTPMailer, get_mailer
from tests.conftest import user_payload
from tests.test_copilot import supported_reply


@pytest.fixture
def mailbox(application, settings, monkeypatch):
    class Mailbox:
        def __init__(self):
            self.messages = []
            self.failure = None
            self.entered = None
            self.release = None
            self.connection_failure = False
    inbox = Mailbox()

    class SMTPConnection:
        def __init__(self, *args, **kwargs):
            if inbox.connection_failure:
                raise OSError("private network detail")
        def ehlo(self):
            return 250, b"local SMTP"
        def close(self):
            pass
        def send_message(self, message, **kwargs):
            inbox.messages.append(message)
            if inbox.entered is not None:
                inbox.entered.set()
                assert inbox.release.wait(10), "SMTP test was not released"
            if inbox.failure:
                raise inbox.failure
            return {}
    monkeypatch.setattr(smtplib, "SMTP", SMTPConnection)
    mailer = SMTPMailer(settings.model_copy(update={"smtp_host": "localhost", "smtp_port": 1025, "smtp_security": "none", "smtp_from": "support@example.com"}))
    application.dependency_overrides[get_mailer] = lambda: mailer
    return inbox


@pytest.fixture
def message_factory(client):
    def create(ticket, kind="reply", body="Reviewed support reply.", **extra):
        response = client.post(f"/api/tickets/{ticket['id']}/messages", json={"kind": kind, "body": body, "ticket_version": ticket["version"], **extra})
        assert response.status_code == 201, response.text
        return response.json()
    return create


def approve(client, ticket, message):
    response = client.post(f"/api/tickets/{ticket['id']}/messages/{message['id']}/approve", json={"version": message["version"], "ticket_version": ticket["version"]})
    assert response.status_code == 200, response.text
    return response.json()


def test_review_approval_and_delivery_are_distinct_persistent_transitions(client, ticket_factory, message_factory, mailbox, member):
    ticket = ticket_factory()
    message = message_factory(ticket, body="Unreviewed text.")
    path = f"/api/tickets/{ticket['id']}/messages/{message['id']}"
    refused = client.post(path + "/send", json={"version": 1, "ticket_version": 1})
    assert refused.status_code == 409
    assert mailbox.messages == []
    edited = client.patch(path, json={"version": 1, "ticket_version": 1, "body": "  Human-reviewed reply.\nNo private note included.  "})
    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert client.patch(path, json={"version": 1, "ticket_version": 1, "body": "Lost update"}).status_code == 409
    approved = approve(client, ticket, edited.json())
    assert approved["delivery_status"] == "approved"
    assert approved["approved_by"]["id"] == str(member.id)
    assert approved["recipient_email"] == ticket["customer_email"]
    assert mailbox.messages == []
    current = client.get(f"/api/tickets/{ticket['id']}").json()
    assert current["sla"]["first_response"]["completed_at"] is None
    assert client.patch(path, json={"version": approved["version"], "ticket_version": current["version"], "body": "Changed after approval"}).status_code == 409
    payload = {"version": approved["version"], "ticket_version": current["version"]}
    sent = client.post(path + "/send", json=payload)
    assert sent.status_code == 200
    assert sent.json()["delivery_status"] == "sent"
    assert sent.json()["body"] == "Human-reviewed reply.\nNo private note included."
    assert len(mailbox.messages) == 1
    assert mailbox.messages[0]["To"] == ticket["customer_email"]
    assert mailbox.messages[0].get_content().strip() == sent.json()["body"]
    assert client.post(path + "/send", json=payload).json() == sent.json()
    assert len(mailbox.messages) == 1
    messages = client.get(f"/api/tickets/{ticket['id']}/messages").json()
    assert messages == [sent.json()]
    current = client.get(f"/api/tickets/{ticket['id']}").json()
    assert current["sla"]["first_response"]["completed_at"] == sent.json()["sent_at"]
    assert current["status"] == "open" and current["sla"]["resolution"]["completed_at"] is None
    events = client.get(f"/api/tickets/{ticket['id']}/events").json()
    assert [event["actor"]["id"] for event in events] == [str(member.id)] * 3
    assert "reply_approved" in events[-2]["changes"] and "reply_sent" in events[-1]["changes"]


def test_customer_messages_and_notes_preserve_history_and_invalidate_old_drafts(client, ticket_factory, message_factory, mailbox):
    ticket = ticket_factory()
    draft = message_factory(ticket)
    note = message_factory(ticket, kind="note", body="Private account investigation.")
    current = client.get(f"/api/tickets/{ticket['id']}").json()
    assert current["version"] == 2 and note["delivery_status"] == "not_applicable"
    path = f"/api/tickets/{ticket['id']}/messages/{draft['id']}"
    stale = client.post(path + "/approve", json={"version": 1, "ticket_version": 2})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_reply"
    saved = client.patch(path, json={"version": 1, "ticket_version": 2, "body": "Reply reviewed with new context."})
    assert saved.status_code == 200
    approved = approve(client, current, saved.json())
    current = client.get(f"/api/tickets/{ticket['id']}").json()
    message_factory(current, kind="customer", body="One more detail from the customer.")
    latest = client.get(f"/api/tickets/{ticket['id']}").json()
    blocked = client.post(path + "/send", json={"version": approved["version"], "ticket_version": latest["version"]})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "stale_reply"
    assert mailbox.messages == []
    assert latest["sla"]["first_response"]["completed_at"] is None
    note_path = f"/api/tickets/{ticket['id']}/messages/{note['id']}"
    assert client.post(note_path + "/approve", json={"version": 1, "ticket_version": latest["version"]}).status_code == 409
    assert client.post(note_path + "/send", json={"version": 1, "ticket_version": latest["version"]}).status_code == 409


def test_only_one_editable_draft_is_created_even_concurrently(client, ticket_factory):
    ticket = ticket_factory()
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(lambda body: client.post(f"/api/tickets/{ticket['id']}/messages", json={"kind": "reply", "body": body, "ticket_version": 1}), ["First draft", "Second draft"]))
    assert sorted(response.status_code for response in attempts) == [201, 409]
    winner = next(response.json() for response in attempts if response.status_code == 201)
    assert client.get(f"/api/tickets/{ticket['id']}/messages").json() == [winner]


@pytest.mark.parametrize("failure,status,code,retryable", [
    (smtplib.SMTPDataError(550, b"private SMTP rejection"), "failed", "smtp_rejected", True),
    (smtplib.SMTPServerDisconnected("private socket information"), "unknown", "smtp_delivery_unconfirmed", False),
])
def test_smtp_outcomes_are_honest_and_uncertain_delivery_cannot_be_retried(client, ticket_factory, message_factory, mailbox, failure, status, code, retryable):
    ticket = ticket_factory()
    approved = approve(client, ticket, message_factory(ticket))
    path = f"/api/tickets/{ticket['id']}/messages/{approved['id']}/send"
    mailbox.failure = failure
    result = client.post(path, json={"version": approved["version"], "ticket_version": approved["ticket_version"]})
    assert result.status_code == 200
    outcome = result.json()
    assert outcome["delivery_status"] == status and outcome["delivery_error"] == code
    assert outcome["sent_at"] is None
    assert "private" not in result.text
    current = client.get(f"/api/tickets/{ticket['id']}").json()
    assert current["sla"]["first_response"]["completed_at"] is None
    mailbox.failure = None
    retry = client.post(path, json={"version": outcome["version"], "ticket_version": current["version"]})
    if retryable:
        assert retry.status_code == 200 and retry.json()["delivery_status"] == "sent"
        assert retry.json()["smtp_message_id"] == outcome["smtp_message_id"]
        assert len(mailbox.messages) == 2
    else:
        assert retry.status_code == 409 and retry.json()["detail"]["code"] == "delivery_unknown"
        assert len(mailbox.messages) == 1


def test_smtp_connection_failure_preserves_retryable_approval(client, ticket_factory, message_factory, mailbox):
    ticket = ticket_factory()
    approved = approve(client, ticket, message_factory(ticket))
    mailbox.connection_failure = True
    result = client.post(f"/api/tickets/{ticket['id']}/messages/{approved['id']}/send", json={"version": approved["version"], "ticket_version": approved["ticket_version"]})
    assert result.status_code == 200
    assert result.json()["delivery_status"] == "failed"
    assert result.json()["delivery_error"] == "smtp_connection_failed"
    assert mailbox.messages == []


def test_parallel_send_does_not_hold_ticket_lock_or_duplicate_smtp(client, ticket_factory, message_factory, mailbox):
    ticket = ticket_factory()
    approved = approve(client, ticket, message_factory(ticket))
    path = f"/api/tickets/{ticket['id']}/messages/{approved['id']}/send"
    payload = {"version": approved["version"], "ticket_version": approved["ticket_version"]}
    mailbox.entered, mailbox.release = Event(), Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, path, json=payload)
        try:
            assert mailbox.entered.wait(10)
            duplicate = client.post(path, json=payload)
            assert duplicate.status_code == 409 and duplicate.json()["detail"]["code"] == "delivery_in_progress"
            updated = client.patch(f"/api/tickets/{ticket['id']}", json={"version": payload["ticket_version"], "status": "in_progress"})
            assert updated.status_code == 200
        finally:
            mailbox.release.set()
        sent = pending.result(timeout=10)
    assert sent.status_code == 200 and sent.json()["delivery_status"] == "sent"
    current = client.get(f"/api/tickets/{ticket['id']}").json()
    assert current["status"] == "in_progress" and current["version"] == 4
    assert len(mailbox.messages) == 1


def test_copilot_uses_customer_and_sent_replies_but_never_notes_or_unsent_drafts(client, ticket_factory, message_factory, document_factory, provider, mailbox):
    document_factory()
    ticket = ticket_factory()
    message_factory(ticket, kind="note", body="INTERNAL_ONLY_PRIVATE")
    ticket = client.get(f"/api/tickets/{ticket['id']}").json()
    message_factory(ticket, kind="customer", body="CUSTOMER_VISIBLE I still need a password reset.")
    ticket = client.get(f"/api/tickets/{ticket['id']}").json()
    approved = approve(client, ticket, message_factory(ticket, body="SENT_REPLY_VISIBLE Please use Forgot password."))
    sent = client.post(f"/api/tickets/{ticket['id']}/messages/{approved['id']}/send", json={"version": approved["version"], "ticket_version": approved["ticket_version"]})
    assert sent.json()["delivery_status"] == "sent"
    ticket = client.get(f"/api/tickets/{ticket['id']}").json()
    message_factory(ticket, body="UNSENT_DRAFT_PRIVATE")
    provider.chat_handler = supported_reply
    analyzed = client.post(f"/api/tickets/{ticket['id']}/analyze", json={"version": ticket["version"]})
    assert analyzed.status_code == 201, analyzed.text
    context = json.dumps(user_payload(provider.calls_for("chat/completions")[-1].body))
    assert "CUSTOMER_VISIBLE" in context and "SENT_REPLY_VISIBLE" in context
    assert "INTERNAL_ONLY_PRIVATE" not in context and "UNSENT_DRAFT_PRIVATE" not in context
    embedded = json.dumps(provider.calls_for("embeddings")[-1].body)
    assert "INTERNAL_ONLY_PRIVATE" not in embedded and "UNSENT_DRAFT_PRIVATE" not in embedded


def test_ai_draft_provenance_rejects_other_ticket_or_stale_analysis(client, ticket_factory, message_factory, document_factory, provider):
    document_factory()
    ticket = ticket_factory()
    provider.chat_handler = supported_reply
    run = client.post(f"/api/tickets/{ticket['id']}/analyze", json={"version": 1}).json()
    other = ticket_factory()
    rejected = client.post(f"/api/tickets/{other['id']}/messages", json={"kind": "reply", "body": "Wrong source", "source_run_id": run["id"], "ticket_version": 1})
    assert rejected.status_code == 422
    draft = message_factory(ticket, source_run_id=run["id"])
    changed = client.patch(f"/api/tickets/{ticket['id']}", json={"version": 1, "title": "Changed customer request"}).json()
    reviewed = client.patch(f"/api/tickets/{ticket['id']}/messages/{draft['id']}", json={"version": 1, "ticket_version": changed["version"], "body": "Manually reviewed for new context."})
    assert reviewed.status_code == 200 and reviewed.json()["source_run_id"] is None
    stale = client.post(f"/api/tickets/{ticket['id']}/messages", json={"kind": "reply", "body": "Stale source", "source_run_id": run["id"], "ticket_version": changed["version"]})
    assert stale.status_code == 409


@pytest.mark.parametrize("payload", [{"body": " "}, {"body": "x" * 10001}, {"kind": "system"}, {"ticket_version": True}, {"ticket_version": 0}, {"author_id": "injected"}])
def test_invalid_message_does_not_mutate_ticket(client, ticket_factory, payload):
    ticket = ticket_factory()
    response = client.post(f"/api/tickets/{ticket['id']}/messages", json={"kind": "note", "body": "Valid note", "ticket_version": 1, **payload})
    assert response.status_code == 422
    assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    assert client.get(f"/api/tickets/{ticket['id']}/messages").json() == []
