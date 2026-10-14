from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.automation_schemas import CalendarPatch, CalendarRead, RuleCreate, RuleOrder, RulePatch, RuleRead
from app.errors import DomainError
from app.models import AssignmentRule, BusinessCalendar, Member, Ticket


def calendar_row(session: Session, *, lock: bool = False) -> BusinessCalendar:
    query = select(BusinessCalendar).where(BusinessCalendar.id == 1)
    row = session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise DomainError("automation_not_configured")
    return row


def read_calendar(sessions: sessionmaker[Session]) -> CalendarRead:
    with sessions() as session:
        return CalendarRead.model_validate(calendar_row(session))


def patch_calendar(sessions: sessionmaker[Session], payload: CalendarPatch) -> CalendarRead:
    with sessions.begin() as session:
        row = calendar_row(session, lock=True)
        if row.version != payload.version:
            raise DomainError("calendar_conflict")
        for key, value in payload.model_dump(mode="json", exclude={"version"}).items():
            setattr(row, key, value)
        row.version += 1
        return CalendarRead.model_validate(row)


def rule_read(row: AssignmentRule) -> RuleRead:
    return RuleRead(id=row.id, name=row.name, enabled=row.enabled, position=row.position,
        priority=row.priority, customer_domain=row.customer_domain, subject_contains=row.subject_contains,
        assignee_id=row.assignee_id, version=row.version,
        catch_all=not any((row.priority, row.customer_domain, row.subject_contains)))


def list_rules(sessions: sessionmaker[Session]) -> list[RuleRead]:
    with sessions() as session:
        return [rule_read(row) for row in session.scalars(select(AssignmentRule).order_by(AssignmentRule.position, AssignmentRule.id))]


def eligible(session: Session, agent_id: UUID) -> bool:
    return session.scalar(select(Member.id).where(Member.agent_id == agent_id, Member.active.is_(True))) is not None


def create_rule(sessions: sessionmaker[Session], payload: RuleCreate) -> RuleRead:
    with sessions.begin() as session:
        calendar_row(session, lock=True)
        if not eligible(session, payload.assignee_id):
            raise DomainError("inactive_rule_assignee")
        row = AssignmentRule(**payload.model_dump(exclude={"catch_all"}), version=1)
        session.add(row)
        session.flush()
        return rule_read(row)


def patch_rule(sessions: sessionmaker[Session], rule_id: UUID, payload: RulePatch) -> RuleRead:
    with sessions.begin() as session:
        calendar_row(session, lock=True)
        row = session.get(AssignmentRule, rule_id)
        if row is None:
            raise DomainError("not_found")
        if row.version != payload.version:
            raise DomainError("assignment_rule_conflict")
        if (payload.enabled or payload.assignee_id != row.assignee_id) and not eligible(session, payload.assignee_id):
            raise DomainError("inactive_rule_assignee")
        for key, value in payload.model_dump(exclude={"catch_all", "version"}).items():
            setattr(row, key, value)
        row.version += 1
        return rule_read(row)


def delete_rule(sessions: sessionmaker[Session], rule_id: UUID, version: int) -> None:
    with sessions.begin() as session:
        calendar_row(session, lock=True)
        row = session.get(AssignmentRule, rule_id)
        if row is None:
            raise DomainError("not_found")
        if row.version != version:
            raise DomainError("assignment_rule_conflict")
        session.delete(row)


def order_rules(sessions: sessionmaker[Session], payload: RuleOrder) -> list[RuleRead]:
    with sessions.begin() as session:
        calendar_row(session, lock=True)
        rows = {row.id: row for row in session.scalars(select(AssignmentRule))}
        if len(payload.rules) != len(rows) or set(rows) != {item.id for item in payload.rules} or any(rows[item.id].version != item.version for item in payload.rules):
            raise DomainError("assignment_rule_conflict")
        result = []
        for index, item in enumerate(payload.rules):
            row = rows[item.id]
            if row.position != index:
                row.position, row.version = index, row.version + 1
            result.append(rule_read(row))
        return result


def apply_assignment(session: Session, ticket: Ticket) -> None:
    if ticket.assignee_id is not None:
        return
    rows = session.scalars(select(AssignmentRule).join(Member, Member.agent_id == AssignmentRule.assignee_id)
        .where(AssignmentRule.enabled.is_(True), Member.active.is_(True))
        .order_by(AssignmentRule.position, AssignmentRule.id))
    domain = ticket.customer_email.rsplit("@", 1)[-1].encode("idna").decode("ascii").lower()
    for rule in rows:
        if rule.priority and rule.priority != ticket.priority:
            continue
        if rule.customer_domain and rule.customer_domain != domain:
            continue
        if rule.subject_contains and rule.subject_contains.casefold() not in ticket.title.casefold():
            continue
        ticket.assignee_id = rule.assignee_id
        break


def sla_alerts(sessions: sessionmaker[Session], limit: int = 50, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    with sessions() as session:
        window = calendar_row(session).alert_minutes
        cutoff = now + timedelta(minutes=window)
        alerts = []
        for target, due_column, completed_column in (
            ("first_response", Ticket.first_response_due_at, Ticket.first_response_at),
            ("resolution", Ticket.resolution_due_at, Ticket.resolved_at),
        ):
            rows = session.execute(select(Ticket.id, Ticket.title, due_column)
                .where(Ticket.status != "resolved", completed_column.is_(None), due_column <= cutoff)
                .order_by(due_column, Ticket.id).limit(limit)).all()
            alerts.extend({"ticket_id": row.id, "title": row.title, "target": target,
                "due_at": row[2], "breached": row[2] < now} for row in rows)
        alerts.sort(key=lambda item: (item["due_at"], str(item["ticket_id"]), item["target"]))
        return {"as_of": now, "window_minutes": window, "items": alerts[:limit]}
