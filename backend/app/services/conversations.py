from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, sessionmaker

from app.errors import DomainError
from app.integrations.mail import OutboundMail, SMTPMailer
from app.models import CopilotRun, Member, Ticket, TicketEvent, TicketMessage
from app.schemas import ActorRead, MemberRead, MessageAction, MessageCreate, MessagePatch, MessageRead
from app.services.tickets import get_ticket


def message_fields(message: TicketMessage, author: Member, approver: Member | None) -> MessageRead:
    return MessageRead(
        id=message.id, ticket_id=message.ticket_id, kind=message.kind, body=message.body,
        author=ActorRead.model_validate(author), source_run_id=message.source_run_id,
        ticket_version=message.ticket_version, version=message.version, delivery_status=message.delivery_status,
        approved_by=ActorRead.model_validate(approver) if approver else None,
        approved_at=message.approved_at, recipient_email=message.recipient_email, subject=message.subject,
        smtp_message_id=message.smtp_message_id, delivery_error=message.delivery_error, sent_at=message.sent_at,
        created_at=message.created_at, updated_at=message.updated_at,
    )


def message_read(session: Session, message: TicketMessage) -> MessageRead:
    author = session.get(Member, message.author_id)
    approver = session.get(Member, message.approved_by_id) if message.approved_by_id else None
    return message_fields(message, author, approver)


def list_messages(sessions: sessionmaker[Session], ticket_id: UUID) -> list[MessageRead]:
    approver = aliased(Member)
    with sessions() as session:
        get_ticket(session, ticket_id)
        rows = session.execute(
            select(TicketMessage, Member, approver)
            .join(Member, Member.id == TicketMessage.author_id)
            .outerjoin(approver, approver.id == TicketMessage.approved_by_id)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at, TicketMessage.id)
        ).all()
        return [message_fields(message, author, approved_by) for message, author, approved_by in rows]


def locked_message(session: Session, ticket_id: UUID, message_id: UUID) -> TicketMessage:
    message = session.scalar(select(TicketMessage).where(
        TicketMessage.id == message_id, TicketMessage.ticket_id == ticket_id,
    ).with_for_update())
    if message is None:
        raise DomainError("not_found")
    return message


def check_versions(ticket: Ticket, message: TicketMessage, payload: MessageAction | MessagePatch) -> None:
    if ticket.version != payload.ticket_version:
        raise DomainError("ticket_conflict")
    if message.version != payload.version:
        raise DomainError("message_conflict")


def record_event(session: Session, ticket: Ticket, message: TicketMessage, actor: MemberRead, action: str) -> None:
    ticket.version += 1
    ticket.updated_at = datetime.now(timezone.utc)
    message.ticket_version = ticket.version
    session.add(TicketEvent(ticket_id=ticket.id, ticket_version=ticket.version, actor_id=actor.id,
                            changes={action: {"old": None, "new": str(message.id)}}))


def create_message(sessions: sessionmaker[Session], ticket_id: UUID, payload: MessageCreate, actor: MemberRead) -> MessageRead:
    try:
        with sessions.begin() as session:
            ticket = get_ticket(session, ticket_id, lock=True)
            if ticket.version != payload.ticket_version:
                raise DomainError("ticket_conflict")
            if payload.source_run_id is not None:
                source = session.get(CopilotRun, payload.source_run_id)
                if source is None or source.ticket_id != ticket.id or not source.grounded:
                    raise DomainError("invalid_source_analysis")
                if source.ticket_version != ticket.version:
                    raise DomainError("ticket_conflict")
            message = TicketMessage(
                ticket_id=ticket.id, kind=payload.kind, body=payload.body, author_id=actor.id,
                source_run_id=payload.source_run_id, ticket_version=ticket.version, version=1,
                delivery_status="draft" if payload.kind == "reply" else "not_applicable",
            )
            session.add(message)
            session.flush()
            if payload.kind != "reply":
                record_event(session, ticket, message, actor, "customer_message" if payload.kind == "customer" else "internal_note")
                session.flush()
            return message_read(session, message)
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_ticket_open_reply_draft":
            raise DomainError("draft_exists") from None
        raise


def patch_message(sessions: sessionmaker[Session], ticket_id: UUID, message_id: UUID, payload: MessagePatch, actor: MemberRead) -> MessageRead:
    with sessions.begin() as session:
        ticket = get_ticket(session, ticket_id, lock=True)
        message = locked_message(session, ticket_id, message_id)
        check_versions(ticket, message, payload)
        if message.kind != "reply" or message.delivery_status != "draft":
            raise DomainError("invalid_message_state")
        if message.ticket_version != ticket.version:
            message.source_run_id = None
        message.body = payload.body
        message.author_id = actor.id
        message.ticket_version = ticket.version
        message.version += 1
        message.updated_at = datetime.now(timezone.utc)
        return message_read(session, message)


def approve_message(sessions: sessionmaker[Session], ticket_id: UUID, message_id: UUID, payload: MessageAction, actor: MemberRead) -> MessageRead:
    with sessions.begin() as session:
        ticket = get_ticket(session, ticket_id, lock=True)
        message = locked_message(session, ticket_id, message_id)
        check_versions(ticket, message, payload)
        if message.kind != "reply" or message.delivery_status != "draft":
            raise DomainError("invalid_message_state")
        if message.ticket_version != ticket.version:
            raise DomainError("stale_reply")
        now = datetime.now(timezone.utc)
        message.delivery_status = "approved"
        message.approved_by_id = actor.id
        message.approved_at = now
        message.updated_at = now
        message.recipient_email = ticket.customer_email
        message.subject = "Re: " + " ".join(ticket.title.split())
        message.version += 1
        record_event(session, ticket, message, actor, "reply_approved")
        session.flush()
        return message_read(session, message)


def send_message(sessions: sessionmaker[Session], ticket_id: UUID, message_id: UUID, payload: MessageAction,
                 actor: MemberRead, mailer: SMTPMailer) -> MessageRead:
    with sessions.begin() as session:
        ticket = get_ticket(session, ticket_id, lock=True)
        message = locked_message(session, ticket_id, message_id)
        if message.delivery_status == "sent":
            return message_read(session, message)
        if message.delivery_status in {"sending", "unknown"}:
            raise DomainError("delivery_in_progress" if message.delivery_status == "sending" else "delivery_unknown")
        check_versions(ticket, message, payload)
        if message.kind != "reply" or message.delivery_status not in {"approved", "failed"}:
            raise DomainError("invalid_message_state")
        if message.ticket_version != ticket.version:
            raise DomainError("stale_reply")
        mailer.require_configured()
        message.smtp_message_id = f"<{message.id}@{str(mailer.settings.smtp_from).rsplit('@', 1)[1]}>"
        message.delivery_status = "sending"
        message.delivery_error = None
        message.version += 1
        message.updated_at = datetime.now(timezone.utc)
        outgoing = OutboundMail(message.recipient_email, message.subject, message.body, message.smtp_message_id)
    # Neither ticket nor message is locked over the SMTP call.
    outcome = mailer.send(outgoing)
    with sessions.begin() as session:
        ticket = get_ticket(session, ticket_id, lock=True)
        message = locked_message(session, ticket_id, message_id)
        now = datetime.now(timezone.utc)
        message.delivery_status = outcome.status
        message.delivery_error = outcome.error
        message.version += 1
        message.updated_at = now
        if outcome.status == "sent":
            message.sent_at = now
            if ticket.first_response_at is None:
                ticket.first_response_at = now
            record_event(session, ticket, message, actor, "reply_sent")
        session.flush()
        return message_read(session, message)
