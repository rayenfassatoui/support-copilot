from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.errors import DomainError
from app.models import Agent, Member, SlaPolicy
from app.schemas import MemberCreate, MemberPatch, MemberRead


def member_read(member: Member) -> MemberRead:
    return MemberRead(
        id=member.id, agent_id=member.agent_id, name=member.name, email=member.email,
        role=member.role, active=member.active, version=member.version,
        registered=member.auth_subject is not None, created_at=member.created_at,
    )


def add_member(session: Session, payload: MemberCreate) -> Member:
    email = str(payload.email).lower()
    if session.scalar(select(Member.id).where(Member.email == email)) is not None:
        raise DomainError("member_exists")
    agent = session.scalar(select(Agent).where(func.lower(Agent.email) == email))
    if agent is None:
        agent = Agent(name=payload.name, email=email)
        session.add(agent)
        session.flush()
    member = Member(agent_id=agent.id, email=email, name=payload.name, role=payload.role, active=True, version=1)
    session.add(member)
    session.flush()
    return member


def bootstrap_admin(sessions: sessionmaker[Session], settings: Settings) -> None:
    if settings.bootstrap_admin_email is None:
        return
    with sessions.begin() as session:
        # This migration-created singleton row serializes first startup across workers.
        session.scalar(select(SlaPolicy).where(SlaPolicy.priority == "medium").with_for_update())
        if session.scalar(select(Member.id).limit(1)) is None:
            add_member(session, MemberCreate(name="Workspace administrator", email=settings.bootstrap_admin_email, role="admin"))


def list_members(sessions: sessionmaker[Session]) -> list[MemberRead]:
    with sessions() as session:
        return [member_read(row) for row in session.scalars(select(Member).order_by(Member.name, Member.id))]


def create_member(sessions: sessionmaker[Session], payload: MemberCreate) -> MemberRead:
    try:
        with sessions.begin() as session:
            return member_read(add_member(session, payload))
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) in {"members_email_key", "agents_email_key"}:
            raise DomainError("member_exists") from None
        raise


def patch_member(sessions: sessionmaker[Session], member_id: UUID, payload: MemberPatch) -> MemberRead:
    with sessions.begin() as session:
        # Lock in one order so simultaneous demotions cannot remove both last admins.
        members = session.scalars(select(Member).order_by(Member.id).with_for_update()).all()
        member = next((row for row in members if row.id == member_id), None)
        if member is None:
            raise DomainError("not_found")
        if member.version != payload.version:
            raise DomainError("member_conflict")
        if member.active and member.role == "admin" and (not payload.active or payload.role != "admin"):
            if not any(row.id != member.id and row.active and row.role == "admin" for row in members):
                raise DomainError("last_admin")
        if member.active != payload.active or member.role != payload.role:
            member.active = payload.active
            member.role = payload.role
            member.version += 1
        return member_read(member)
