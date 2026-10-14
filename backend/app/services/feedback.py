from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.analytics_schemas import FeedbackRequest, FeedbackSubmit
from app.config import Settings
from app.errors import DomainError
from app.models import CustomerFeedback, Ticket, TicketMessage
from app.schemas import MemberRead, MessageRead
from app.services.conversations import message_read
from app.services.tickets import get_ticket


def feedback_status(sessions: sessionmaker[Session], ticket_id: UUID) -> dict:
    with sessions() as session:
        ticket = get_ticket(session, ticket_id)
        row = session.scalar(select(CustomerFeedback).where(CustomerFeedback.ticket_id == ticket.id))
        if row is None:
            return {"requested": False, "active": False, "submitted": False, "rating": None, "comment": None, "expires_at": None}
        active = row.submitted_at is None and row.expires_at > datetime.now(timezone.utc) and ticket.status == "resolved" and ticket.resolved_at is not None and row.created_at >= ticket.resolved_at
        return {"requested": True, "active": active, "submitted": row.submitted_at is not None, "rating": row.rating,
            "comment": row.comment, "expires_at": row.expires_at}


def request_feedback(sessions: sessionmaker[Session], settings: Settings, ticket_id: UUID,
                     payload: FeedbackRequest, actor: MemberRead) -> MessageRead:
    with sessions.begin() as session:
        ticket = get_ticket(session, ticket_id, lock=True)
        if ticket.version != payload.ticket_version:
            raise DomainError("ticket_conflict")
        if ticket.status != "resolved" or ticket.resolved_at is None:
            raise DomainError("feedback_requires_resolved")
        row = session.scalar(select(CustomerFeedback).where(CustomerFeedback.ticket_id == ticket.id).with_for_update())
        now = datetime.now(timezone.utc)
        if row is not None and row.rating is not None:
            raise DomainError("feedback_submitted")
        if row is not None and row.expires_at > now and row.created_at >= ticket.resolved_at:
            raise DomainError("feedback_exists")
        if session.scalar(select(TicketMessage.id).where(TicketMessage.ticket_id == ticket.id,
                TicketMessage.kind == "reply", TicketMessage.delivery_status == "draft")):
            raise DomainError("draft_exists")
        token = secrets.token_urlsafe(32)
        if row is None:
            row = CustomerFeedback(ticket_id=ticket.id)
            session.add(row)
        row.token_hash = hashlib.sha256(token.encode()).hexdigest()
        row.created_at, row.expires_at, row.created_by_id = now, now + timedelta(days=14), actor.id
        link = f"{settings.public_app_url}/feedback#token={token}"
        body = f"How was your support experience?\n\nPlease rate our help from 1 to 5 and share any feedback:\n{link}\n\nThis private link expires in 14 days. Thank you."
        message = TicketMessage(ticket_id=ticket.id, kind="reply", body=body, author_id=actor.id,
            ticket_version=ticket.version, version=1, delivery_status="draft")
        session.add(message)
        session.flush()
        row.message_id = message.id
        return message_read(session, message)


def usable_feedback(session: Session, token: str, *, lock: bool = False) -> CustomerFeedback:
    digest = hashlib.sha256(token.encode()).hexdigest()
    # Ticket first, then survey: same lock order as authenticated survey creation and ticket edits.
    ticket_id = session.scalar(select(CustomerFeedback.ticket_id).where(CustomerFeedback.token_hash == digest))
    if ticket_id is None:
        raise DomainError("feedback_unavailable")
    ticket_query = select(Ticket).where(Ticket.id == ticket_id)
    ticket = session.scalar(ticket_query.with_for_update() if lock else ticket_query)
    query = select(CustomerFeedback).where(CustomerFeedback.ticket_id == ticket_id, CustomerFeedback.token_hash == digest)
    row = session.scalar(query.with_for_update() if lock else query)
    if row is None or row.submitted_at is not None or row.expires_at <= datetime.now(timezone.utc) or ticket.status != "resolved" or ticket.resolved_at is None or row.created_at < ticket.resolved_at:
        raise DomainError("feedback_unavailable")
    return row


def validate_feedback(sessions: sessionmaker[Session], token: str) -> dict:
    with sessions() as session:
        row = usable_feedback(session, token)
        return {"expires_at": row.expires_at}


def submit_feedback(sessions: sessionmaker[Session], payload: FeedbackSubmit) -> dict:
    with sessions.begin() as session:
        row = usable_feedback(session, payload.token, lock=True)
        row.rating, row.comment = payload.rating, payload.comment or None
        row.submitted_at = datetime.now(timezone.utc)
        return {"submitted": True}
