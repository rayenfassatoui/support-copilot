from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from email.message import EmailMessage
from uuid import UUID

import pytest
from sqlalchemy import select

from app.integrations.imap import IncomingMail, MailInputError, parse_mail
from app.models import InboundReceipt, MailboxState, Ticket, TicketMessage
from app.services import mailbox


@pytest.fixture
def mailbox_state(sessions):
    key = "a" * 64
    with sessions.begin() as session:
        session.add(MailboxState(mailbox_key=key, uid_validity=100, last_uid=0))
    return key


def incoming(identifier, sender="customer@example.com", references=None):
    return IncomingMail(sender, "A synthetic support request", "Please review this fictional billing issue.", f"<{identifier}@example.com>", references or [], references[-1] if references else None)


def test_duplicate_ids_and_uids_never_create_duplicate_tickets(sessions, mailbox_state):
    mail = incoming("one")
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda uid: mailbox.record_incoming(sessions, mailbox_state, 100, uid, mail), [1, 2]))
    mailbox.record_incoming(sessions, mailbox_state, 100, 1, mail)
    with sessions() as session:
        assert len(session.scalars(select(Ticket)).all()) == 1
        assert len(session.scalars(select(TicketMessage)).all()) == 1
        assert sorted(session.scalars(select(InboundReceipt.status)).all()) == ["ignored", "imported"]
        assert session.get(MailboxState, mailbox_state).last_uid == 2


def test_replies_reopen_the_same_customer_thread_but_cannot_join_another_customer(sessions, mailbox_state, client):
    mailbox.record_incoming(sessions, mailbox_state, 100, 1, incoming("root"))
    first = client.get("/api/tickets").json()["items"][0]
    closed = client.patch(f"/api/tickets/{first['id']}", json={"version": first["version"], "status": "resolved"}).json()
    mailbox.record_incoming(sessions, mailbox_state, 100, 2, incoming("reply", references=["<root@example.com>"]))
    reopened = client.get(f"/api/tickets/{first['id']}").json()
    assert reopened["status"] == "open" and reopened["version"] == closed["version"] + 1
    assert reopened["sla"]["resolution"]["due_at"] == first["sla"]["resolution"]["due_at"]
    messages = client.get(f"/api/tickets/{first['id']}/messages").json()
    assert [row["smtp_message_id"] for row in messages] == ["<root@example.com>", "<reply@example.com>"]
    assert all(row["author"] is None and row["sender_email"] == "customer@example.com" for row in messages)
    mailbox.record_incoming(sessions, mailbox_state, 100, 3, incoming("outsider", sender="different@example.com", references=["<root@example.com>"]))
    assert client.get("/api/tickets").json()["total"] == 2
    assert len(client.get(f"/api/tickets/{first['id']}/messages").json()) == 2


def test_poison_message_advances_cursor_and_uidvalidity_reset_remains_idempotent(sessions, settings, monkeypatch):
    configured = settings.model_copy(update={"imap_host": "mailbox", "imap_username": "support"})
    validity = 100
    raw = EmailMessage()
    raw["From"] = "customer@example.com"
    raw["Message-ID"] = "<retained@example.com>"
    raw["Subject"] = "A retained request"
    raw.set_content("A valid synthetic message after a malformed email.")

    @contextmanager
    def connection(_):
        yield object(), validity

    monkeypatch.setattr(mailbox, "connect", connection)
    monkeypatch.setattr(mailbox, "pending_uids", lambda connection, cursor, limit: [uid for uid in (1, 2) if uid > cursor])
    monkeypatch.setattr(mailbox, "fetch_mail", lambda connection, uid: b"malformed" if uid == 1 else raw.as_bytes())
    first = mailbox.sync_mailbox(sessions, configured)
    assert sorted(row["status"] for row in first["receipts"]) == ["failed", "imported"]
    validity = 101
    second = mailbox.sync_mailbox(sessions, configured)
    assert sorted(row["status"] for row in second["receipts"]) == ["failed", "failed", "ignored", "imported"]
    with sessions() as session:
        assert len(session.scalars(select(Ticket)).all()) == 1
        state = session.get(MailboxState, mailbox.mailbox_key(configured))
        assert (state.uid_validity, state.last_uid) == (101, 2)


def test_html_import_keeps_visible_text_and_root_reference_without_attachment_payload(settings):
    mail = EmailMessage()
    mail["From"] = "Customer <customer@example.com>"
    mail["Message-ID"] = "<html@example.com>"
    mail["Subject"] = "HTML support request"
    mail["References"] = " ".join(f"<message-{number}@example.com>" for number in range(40))
    mail["In-Reply-To"] = "<newest@example.com>"
    mail.set_content("<html><head><title>Hidden title</title></head><body><p>Visible request</p><script>secret script</script><p>Second paragraph.</p></body></html>", subtype="html")
    mail.add_attachment(b"private attachment bytes", maintype="application", subtype="octet-stream", filename="attachment.bin")
    parsed = parse_mail(mail.as_bytes(), settings)
    assert "Visible request" in parsed.body and "Second paragraph." in parsed.body
    assert "Hidden title" not in parsed.body and "secret script" not in parsed.body and "private attachment" not in parsed.body
    assert parsed.references[0] == "<message-0@example.com>" and parsed.references[-1] == "<newest@example.com>"
    assert parsed.warning == "attachments_kept_in_mailbox"


@pytest.mark.parametrize("header,value,code", [("Subject", "bad\x00subject", "invalid_subject"), ("Message-ID", "<bad\x00id@example.com>", "missing_or_invalid_message_id"), ("Auto-Submitted", "auto-replied", "automated_message"), ("From", "support@example.com", "self_message")])
def test_unusable_mail_headers_do_not_poison_database_import(settings, header, value, code):
    headers = {"From": "customer@example.com", "Subject": "Synthetic request", "Message-ID": "<safe@example.com>", "Content-Type": "text/plain; charset=utf-8"}
    headers[header] = value
    raw = ("\r\n".join(f"{name}: {content}" for name, content in headers.items()) + "\r\n\r\nSynthetic support request.").encode()
    with pytest.raises(MailInputError) as raised:
        parse_mail(raw, settings)
    assert raised.value.code == code
