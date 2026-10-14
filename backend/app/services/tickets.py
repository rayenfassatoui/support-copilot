from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.errors import DomainError
from app.models import Agent, CopilotRun, Member, Ticket, TicketEvent
from app.schemas import ActorRead, AgentRead, AnalysisSummary, MemberRead, TicketCreate, TicketEventRead, TicketListItem, TicketPage, TicketPatch, TicketRead, TicketSearch
from app.services.copilot import run_read
from app.services.sla import snapshot_deadlines, ticket_sla
from app.services.automation import apply_assignment

EDITABLE = ("title", "description", "customer_email", "status", "assignee_id", "priority")


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
        "priority": ticket.priority, "sla": ticket_sla(ticket),
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


def create_ticket(sessions: sessionmaker[Session], payload: TicketCreate, actor: MemberRead) -> TicketRead:
    with sessions.begin() as session:
        ensure_assignee(session, payload.assignee_id)
        now = datetime.now(timezone.utc)
        ticket = Ticket(**payload.model_dump(), status="open", version=1, created_at=now, updated_at=now)
        snapshot_deadlines(session, ticket)
        apply_assignment(session, ticket)
        session.add(ticket)
        session.flush()
        changes = {key: {"old": None, "new": json_value(getattr(ticket, key))} for key in EDITABLE}
        session.add(TicketEvent(ticket_id=ticket.id, ticket_version=1, changes=changes, actor_id=actor.id))
        return ticket_read(session, ticket)


def patch_ticket(sessions: sessionmaker[Session], ticket_id: UUID, payload: TicketPatch, actor: MemberRead) -> TicketRead:
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
            if "priority" in changes:
                snapshot_deadlines(session, ticket)
            if "status" in changes:
                ticket.resolved_at = ticket.updated_at if ticket.status == "resolved" else None
            session.add(TicketEvent(ticket_id=ticket.id, ticket_version=ticket.version, changes=changes, actor_id=actor.id))
            session.flush()
        return ticket_read(session, ticket)


def read_ticket(sessions: sessionmaker[Session], ticket_id: UUID) -> TicketRead:
    with sessions() as session:
        return ticket_read(session, get_ticket(session, ticket_id))


def list_tickets(sessions: sessionmaker[Session], query: TicketSearch, actor: MemberRead) -> TicketPage:
    latest = select(
        CopilotRun.id.label("analysis_id"), CopilotRun.ticket_id, CopilotRun.ticket_version,
        CopilotRun.intent, CopilotRun.priority, CopilotRun.escalation_reasons,
        func.row_number().over(
            partition_by=CopilotRun.ticket_id,
            order_by=(CopilotRun.created_at.desc(), CopilotRun.id.desc()),
        ).label("rank"),
    ).subquery()
    filters = []
    if query.status is not None:
        filters.append(Ticket.status == query.status.value)
    if query.assignee_id is not None:
        filters.append(Ticket.assignee_id == query.assignee_id)
    if query.assignment == "mine":
        filters.append(Ticket.assignee_id == actor.agent_id)
    elif query.assignment == "unassigned":
        filters.append(Ticket.assignee_id.is_(None))
    if query.priority is not None:
        filters.append(Ticket.priority == query.priority)
    if query.intent is not None:
        filters.append(latest.c.intent == query.intent)
    if query.q:
        pattern = "%" + query.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        filters.append(or_(*(column.ilike(pattern, escape="\\") for column in (Ticket.title, Ticket.description, Ticket.customer_email))))
    now = datetime.now(timezone.utc)
    response_open = Ticket.first_response_at.is_(None)
    resolution_open = Ticket.resolved_at.is_(None)
    if query.sla == "breached":
        filters.append(or_(response_open & (Ticket.first_response_due_at < now), resolution_open & (Ticket.resolution_due_at < now)))
    order = [Ticket.updated_at.desc(), Ticket.id.desc()]
    if query.sort == "priority":
        order.insert(0, case({"urgent": 0, "high": 1, "medium": 2, "low": 3}, value=Ticket.priority))
    elif query.sort == "due":
        due = func.least(case((response_open, Ticket.first_response_due_at)), case((resolution_open, Ticket.resolution_due_at)))
        order.insert(0, due.asc().nulls_last())
    base = select(Ticket).outerjoin(latest, (latest.c.ticket_id == Ticket.id) & (latest.c.rank == 1)).where(*filters)
    with sessions() as session:
        total = session.scalar(select(func.count()).select_from(base.subquery()))
        rows = session.execute(
            base.add_columns(Agent, latest.c.analysis_id, latest.c.ticket_version, latest.c.intent,
                             latest.c.priority, latest.c.escalation_reasons)
            .outerjoin(Agent, Ticket.assignee_id == Agent.id)
            .order_by(*order).limit(query.limit).offset(query.offset)
        ).all()
        items = [
            TicketListItem(
                **ticket_fields(ticket, agent),
                latest_analysis=AnalysisSummary(id=run_id, intent=intent, priority=priority,
                                                escalation_recommended=bool(reasons)) if run_id else None,
                analysis_stale=bool(run_id and run_version != ticket.version),
            ) for ticket, agent, run_id, run_version, intent, priority, reasons in rows
        ]
        return TicketPage(items=items, total=total, limit=query.limit, offset=query.offset)


def list_events(sessions: sessionmaker[Session], ticket_id: UUID) -> list[TicketEventRead]:
    with sessions() as session:
        get_ticket(session, ticket_id)
        rows = session.execute(
            select(TicketEvent, Member).outerjoin(Member, TicketEvent.actor_id == Member.id)
            .where(TicketEvent.ticket_id == ticket_id).order_by(TicketEvent.created_at, TicketEvent.id)
        ).all()
        return [TicketEventRead(
            id=event.id, ticket_id=event.ticket_id, ticket_version=event.ticket_version,
            changes=event.changes, created_at=event.created_at,
            actor=ActorRead.model_validate(member) if member else None,
        ) for event, member in rows]
