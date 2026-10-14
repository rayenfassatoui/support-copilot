from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.errors import DomainError
from app.models import SavedView
from app.schemas import MemberRead, SavedViewCreate, SavedViewPatch, SavedViewRead
from app.services.tickets import ensure_assignee


def owned_view(session: Session, view_id: UUID, owner_id: UUID) -> SavedView:
    view = session.scalar(select(SavedView).where(SavedView.id == view_id, SavedView.owner_id == owner_id).with_for_update())
    if view is None:
        raise DomainError("not_found")
    return view


def list_views(sessions: sessionmaker[Session], actor: MemberRead) -> list[SavedViewRead]:
    with sessions() as session:
        rows = session.scalars(select(SavedView).where(SavedView.owner_id == actor.id).order_by(SavedView.name, SavedView.id))
        return [SavedViewRead.model_validate(row) for row in rows]


def create_view(sessions: sessionmaker[Session], payload: SavedViewCreate, actor: MemberRead) -> SavedViewRead:
    try:
        with sessions.begin() as session:
            ensure_assignee(session, payload.filters.assignee_id)
            view = SavedView(owner_id=actor.id, name=payload.name, filters=payload.filters.model_dump(mode="json"), version=1)
            session.add(view)
            session.flush()
            return SavedViewRead.model_validate(view)
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_saved_view_owner_name":
            raise DomainError("view_exists") from None
        raise


def patch_view(sessions: sessionmaker[Session], view_id: UUID, payload: SavedViewPatch, actor: MemberRead) -> SavedViewRead:
    try:
        with sessions.begin() as session:
            view = owned_view(session, view_id, actor.id)
            if view.version != payload.version:
                raise DomainError("view_conflict")
            ensure_assignee(session, payload.filters.assignee_id)
            filters = payload.filters.model_dump(mode="json")
            if view.name != payload.name or view.filters != filters:
                view.name = payload.name
                view.filters = filters
                view.version += 1
            session.flush()
            return SavedViewRead.model_validate(view)
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_saved_view_owner_name":
            raise DomainError("view_exists") from None
        raise


def delete_view(sessions: sessionmaker[Session], view_id: UUID, version: int, actor: MemberRead) -> None:
    with sessions.begin() as session:
        view = owned_view(session, view_id, actor.id)
        if view.version != version:
            raise DomainError("view_conflict")
        session.delete(view)
