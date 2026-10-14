from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.errors import DomainError
from app.models import Agent, CopilotRun, Ticket, TicketEvent
from app.schemas import AgentRead, AnalysisSummary, TicketCreate, TicketEventRead, TicketListItem, TicketPage, TicketPatch, TicketRead
from app.services.copilot import run_read

EDITABLE = ("title", "description", "customer_email", "status", "assignee_id")


def get_ticket(session: Session, ticket_id: UUID, *, lock: bool = False) -> Ticket:
    query = select(Ticket).where(Ticket.id == ticket_id)
    if lock:
        query = query.with_for_update()
    ticket = session.scalar(query)
    if ticket is None:
        raise DomainError("not_found")
    return ticket


def ensure_assignee(session: Session, assignee_id: UUID | None) -> None:
    if assignee_id is not None and session.get(Agent, assignee_id) is None:
        raise DomainError("invalid_assignee")


def ticket_fields(ticket: Ticket, agent: Agent | None) -> dict:
    return {
        "id": ticket.id, "title": ticket.title, "description": ticket.description,
        "customer_email": ticket.customer_email, "status": ticket.status,
        "assignee_id": ticket.assignee_id, "version": ticket.version,
        "created_at": ticket.created_at, "updated_at": ticket.updated_at,
        "assignee": AgentRead.model_validate(agent) if agent else None,
    }


def ticket_read(session: Session, ticket: Ticket) -> TicketRead:
    agent = session.get(Agent, ticket.assignee_id) if ticket.assignee_id else None
    run = session.scalar(
        select(CopilotRun).where(CopilotRun.ticket_id == ticket.id)
        .order_by(CopilotRun.created_at.desc(), CopilotRun.id.desc()).limit(1)
    )
    return TicketRead(
        **ticket_fields(ticket, agent),
        latest_analysis=run_read(session, run) if run else None,
        analysis_stale=bool(run and run.ticket_version != ticket.version),
    )


def json_value(value):
    return str(value) if isinstance(value, UUID) else value


def create_ticket(sessions: sessionmaker[Session], payload: TicketCreate) -> TicketRead:
    with sessions.begin() as session:
        ensure_assignee(session, payload.assignee_id)
        ticket = Ticket(**payload.model_dump(), status="open", version=1)
        session.add(ticket)
        session.flush()
        changes = {key: {"old": None, "new": json_value(getattr(ticket, key))} for key in EDITABLE}
        session.add(TicketEvent(ticket_id=ticket.id, ticket_version=1, changes=changes))
        return ticket_read(session, ticket)


def patch_ticket(sessions: sessionmaker[Session], ticket_id: UUID, payload: TicketPatch) -> TicketRead:
    with sessions.begin() as session:
        ticket = get_ticket(session, ticket_id, lock=True)
        if ticket.version != payload.version:
            raise DomainError("ticket_conflict")
        values = payload.model_dump(exclude_unset=True, mode="python")
        if "assignee_id" in values:
            ensure_assignee(session, values["assignee_id"])
        changes = {}
        for key in EDITABLE:
            if key in values:
                new = values[key].value if key == "status" else values[key]
                old = getattr(ticket, key)
                if old != new:
                    changes[key] = {"old": json_value(old), "new": json_value(new)}
                    setattr(ticket, key, new)
        if changes:
            ticket.version += 1
            ticket.updated_at = datetime.now(timezone.utc)
            session.add(TicketEvent(ticket_id=ticket.id, ticket_version=ticket.version, changes=changes))
            session.flush()
        return ticket_read(session, ticket)


def read_ticket(sessions: sessionmaker[Session], ticket_id: UUID) -> TicketRead:
    with sessions() as session:
        return ticket_read(session, get_ticket(session, ticket_id))


def list_tickets(sessions: sessionmaker[Session], status: str | None, assignee_id: UUID | None, limit: int, offset: int) -> TicketPage:
    filters = []
    if status is not None:
        filters.append(Ticket.status == status)
    if assignee_id is not None:
        filters.append(Ticket.assignee_id == assignee_id)
    with sessions() as session:
        latest = select(
            CopilotRun.id.label("analysis_id"), CopilotRun.ticket_id, CopilotRun.ticket_version,
            CopilotRun.intent, CopilotRun.priority, CopilotRun.escalation_reasons,
            func.row_number().over(
                partition_by=CopilotRun.ticket_id,
                order_by=(CopilotRun.created_at.desc(), CopilotRun.id.desc()),
            ).label("rank"),
        ).subquery()
        total = session.scalar(select(func.count()).select_from(Ticket).where(*filters))
        rows = session.execute(
            select(Ticket, Agent, latest.c.analysis_id, latest.c.ticket_version, latest.c.intent,
                   latest.c.priority, latest.c.escalation_reasons)
            .outerjoin(Agent, Ticket.assignee_id == Agent.id)
            .outerjoin(latest, (latest.c.ticket_id == Ticket.id) & (latest.c.rank == 1))
            .where(*filters).order_by(Ticket.updated_at.desc(), Ticket.id.desc()).limit(limit).offset(offset)
        ).all()
        items = [
            TicketListItem(
                **ticket_fields(ticket, agent),
                latest_analysis=AnalysisSummary(id=run_id, intent=intent, priority=priority,
                                                escalation_recommended=bool(reasons)) if run_id else None,
                analysis_stale=bool(run_id and run_version != ticket.version),
            ) for ticket, agent, run_id, run_version, intent, priority, reasons in rows
        ]
        return TicketPage(items=items, total=total, limit=limit, offset=offset)


def list_events(sessions: sessionmaker[Session], ticket_id: UUID) -> list[TicketEventRead]:
    with sessions() as session:
        get_ticket(session, ticket_id)
        rows = session.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket_id).order_by(TicketEvent.created_at, TicketEvent.id))
        return [TicketEventRead.model_validate(row) for row in rows]
