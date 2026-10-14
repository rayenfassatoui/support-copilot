from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.errors import DomainError
from app.models import SlaPolicy, Ticket
from app.schemas import SlaPolicyPatch, SlaPolicyRead, SlaTarget, TicketSla

DEFAULT_POLICIES = (("urgent", 60, 240), ("high", 240, 1440), ("medium", 480, 2880), ("low", 1440, 7200))


def snapshot_deadlines(session: Session, ticket: Ticket) -> None:
    policy = session.get(SlaPolicy, ticket.priority)
    if policy is None:
        raise DomainError("sla_not_configured")
    ticket.first_response_due_at = ticket.created_at + timedelta(minutes=policy.first_response_minutes)
    ticket.resolution_due_at = ticket.created_at + timedelta(minutes=policy.resolution_minutes)


def target(due_at: datetime, completed_at: datetime | None, now: datetime) -> SlaTarget:
    status = "met" if completed_at is not None and completed_at <= due_at else "on_track"
    if (completed_at or now) > due_at:
        status = "breached"
    return SlaTarget(due_at=due_at, completed_at=completed_at, status=status)


def ticket_sla(ticket: Ticket, now: datetime | None = None) -> TicketSla:
    now = now or datetime.now(timezone.utc)
    return TicketSla(
        first_response=target(ticket.first_response_due_at, ticket.first_response_at, now),
        resolution=target(ticket.resolution_due_at, ticket.resolved_at, now),
    )


def list_policies(sessions: sessionmaker[Session]) -> list[SlaPolicyRead]:
    with sessions() as session:
        rows = {row.priority: row for row in session.scalars(select(SlaPolicy))}
        return [SlaPolicyRead.model_validate(rows[priority]) for priority, _, _ in DEFAULT_POLICIES if priority in rows]


def patch_policy(sessions: sessionmaker[Session], priority: str, payload: SlaPolicyPatch) -> SlaPolicyRead:
    with sessions.begin() as session:
        policy = session.scalar(select(SlaPolicy).where(SlaPolicy.priority == priority).with_for_update())
        if policy is None:
            raise DomainError("not_found")
        if policy.version != payload.version:
            raise DomainError("policy_conflict")
        if (policy.first_response_minutes, policy.resolution_minutes) != (payload.first_response_minutes, payload.resolution_minutes):
            policy.first_response_minutes = payload.first_response_minutes
            policy.resolution_minutes = payload.resolution_minutes
            policy.version += 1
        return SlaPolicyRead.model_validate(policy)
