import asyncio
from datetime import datetime, timezone
import hashlib
import imaplib
import logging
from time import monotonic
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.errors import DomainError
from app.integrations.imap import IncomingMail, MailInputError, connect, fetch_mail, mailbox_key, parse_mail, pending_uids
from app.models import InboundReceipt, MailboxState, Ticket, TicketEvent, TicketMessage
from app.services.automation import apply_assignment
from app.services.sla import snapshot_deadlines

logger = logging.getLogger("copilot.mailbox")


def ensure_state(session: Session, key: str) -> MailboxState:
    session.execute(insert(MailboxState).values(mailbox_key=key, uid_validity=0, last_uid=0).on_conflict_do_nothing())
    return session.scalar(select(MailboxState).where(MailboxState.mailbox_key == key).with_for_update())


def record_incoming(sessions: sessionmaker[Session], key: str, validity: int, uid: int,
                    mail: IncomingMail | None, failure: MailInputError | None = None) -> None:
    with sessions.begin() as session:
        state = ensure_state(session, key)
        if state.uid_validity != validity:
            raise DomainError("mailbox_unavailable")
        if session.scalar(select(InboundReceipt.id).where(InboundReceipt.mailbox_key == key,
                InboundReceipt.uid_validity == validity, InboundReceipt.uid == uid)):
            state.last_uid = max(state.last_uid, uid)
            return
        receipt = InboundReceipt(mailbox_key=key, uid_validity=validity, uid=uid,
            message_id=mail.message_id if mail else None, status="imported", error=mail.warning if mail else None)
        session.add(receipt)
        if failure:
            receipt.status = "ignored" if failure.ignored else "failed"
            receipt.error = failure.code
        elif mail is not None:
            # Across workers/configurations, serialize the same Message-ID only during DB work.
            lock = int.from_bytes(hashlib.sha256(mail.message_id.encode()).digest()[:8], "big", signed=True)
            session.execute(select(func.pg_advisory_xact_lock(lock)))
            if session.scalar(select(TicketMessage.id).where(TicketMessage.smtp_message_id == mail.message_id)):
                receipt.status, receipt.error = "ignored", "duplicate_message"
            else:
                ticket_id = None
                if mail.references:
                    candidates = dict(session.execute(select(TicketMessage.smtp_message_id, TicketMessage.ticket_id)
                        .join(Ticket, Ticket.id == TicketMessage.ticket_id)
                        .where(TicketMessage.smtp_message_id.in_(mail.references), func.lower(Ticket.customer_email) == mail.sender)).all())
                    ticket_id = next((candidates[ref] for ref in reversed(mail.references) if ref in candidates), None)
                now = datetime.now(timezone.utc)
                if ticket_id:
                    ticket = session.scalar(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
                    # Re-check identity after acquiring the ticket lock; an agent may have edited it.
                    if ticket.customer_email.lower() != mail.sender:
                        ticket = None
                else:
                    ticket = None
                changes = {}
                if ticket is None:
                    ticket = Ticket(id=uuid4(), title=mail.subject if len(mail.subject) >= 3 else f"Email: {mail.subject}",
                        description=mail.body if len(mail.body) >= 10 else f"Customer email:\n{mail.body}",
                        customer_email=mail.sender, status="open", priority="medium", version=1, created_at=now, updated_at=now)
                    snapshot_deadlines(session, ticket)
                    apply_assignment(session, ticket)
                    session.add(ticket)
                    session.flush()
                    changes["source"] = {"old": None, "new": "email"}
                    changes["assignee_id"] = {"old": None, "new": str(ticket.assignee_id) if ticket.assignee_id else None}
                else:
                    ticket.version += 1
                    ticket.updated_at = now
                    if ticket.status == "resolved":
                        changes["status"] = {"old": "resolved", "new": "open"}
                        ticket.status, ticket.resolved_at = "open", None
                message = TicketMessage(id=uuid4(), ticket_id=ticket.id, kind="customer", body=mail.body,
                    author_id=None, sender_email=mail.sender, subject=mail.subject,
                    smtp_message_id=mail.message_id, references=mail.references, in_reply_to=mail.in_reply_to,
                    ticket_version=ticket.version, version=1, delivery_status="not_applicable", created_at=now, updated_at=now)
                session.add(message)
                session.flush()
                changes["customer_message"] = {"old": None, "new": str(message.id)}
                session.add(TicketEvent(ticket_id=ticket.id, ticket_version=ticket.version, actor_id=None, changes=changes))
                receipt.ticket_id, receipt.ticket_message_id = ticket.id, message.id
        state.last_uid = max(state.last_uid, uid)


def status(sessions: sessionmaker[Session], settings: Settings) -> dict:
    key = mailbox_key(settings)
    with sessions() as session:
        state = session.get(MailboxState, key)
        rows = session.scalars(select(InboundReceipt).where(InboundReceipt.mailbox_key == key)
            .order_by(InboundReceipt.created_at.desc(), InboundReceipt.id.desc()).limit(50)).all()
        return {"configured": bool(settings.imap_host), "folder": settings.imap_folder,
            "delivery_mode": settings.mail_delivery_mode, "poll_seconds": settings.mailbox_poll_seconds,
            "last_synced_at": state.last_synced_at if state else None, "last_error": state.last_error if state else None,
            "receipts": [{"id": row.id, "status": row.status, "error": row.error, "ticket_id": row.ticket_id,
                "created_at": row.created_at} for row in rows]}


def sync_mailbox(sessions: sessionmaker[Session], settings: Settings, stop: asyncio.Event | None = None) -> dict:
    if not settings.imap_host:
        raise DomainError("mailbox_not_configured")
    key = mailbox_key(settings)
    try:
        with connect(settings) as (connection, validity):
            with sessions.begin() as session:
                state = ensure_state(session, key)
                if state.uid_validity != validity:
                    state.uid_validity, state.last_uid = validity, 0
                last_uid = state.last_uid
            deadline = monotonic() + 30
            for uid in pending_uids(connection, last_uid, settings.imap_batch_size):
                if monotonic() >= deadline or (stop is not None and stop.is_set()):
                    break
                try:
                    mail = parse_mail(fetch_mail(connection, uid), settings)
                except MailInputError as failure:
                    record_incoming(sessions, key, validity, uid, None, failure)
                else:
                    record_incoming(sessions, key, validity, uid, mail)
            with sessions.begin() as session:
                state = ensure_state(session, key)
                state.last_synced_at, state.last_error = datetime.now(timezone.utc), None
    except (OSError, imaplib.IMAP4.error, ValueError):
        with sessions.begin() as session:
            ensure_state(session, key).last_error = "imap_connection_failed"
        raise DomainError("mailbox_unavailable") from None
    return status(sessions, settings)


async def poll_mailbox(sessions: sessionmaker[Session], settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.to_thread(sync_mailbox, sessions, settings, stop)
        except Exception as error:
            logger.error("mailbox_sync category=%s", type(error).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.mailbox_poll_seconds)
        except TimeoutError:
            pass
