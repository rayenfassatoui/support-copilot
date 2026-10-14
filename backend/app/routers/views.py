from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session, sessionmaker

from app.auth import current_member
from app.db import get_sessions
from app.schemas import MemberRead, SavedViewCreate, SavedViewPatch, SavedViewRead
from app.services import views

router = APIRouter(prefix="/views", tags=["saved views"])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]
Actor = Annotated[MemberRead, Depends(current_member)]


@router.get("", response_model=list[SavedViewRead])
def list_views(sessions: Sessions, actor: Actor):
    return views.list_views(sessions, actor)


@router.post("", response_model=SavedViewRead, status_code=201)
def create_view(payload: SavedViewCreate, sessions: Sessions, actor: Actor):
    return views.create_view(sessions, payload, actor)


@router.patch("/{view_id}", response_model=SavedViewRead)
def patch_view(view_id: UUID, payload: SavedViewPatch, sessions: Sessions, actor: Actor):
    return views.patch_view(sessions, view_id, payload, actor)


@router.delete("/{view_id}", status_code=204)
def delete_view(view_id: UUID, sessions: Sessions, actor: Actor, version: Annotated[int, Query(ge=1)]):
    views.delete_view(sessions, view_id, version, actor)
    return Response(status_code=204)
