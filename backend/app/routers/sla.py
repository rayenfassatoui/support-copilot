from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, sessionmaker

from app.auth import current_member, require_admin
from app.db import get_sessions
from app.schemas import Priority, SlaPolicyPatch, SlaPolicyRead
from app.services import sla

router = APIRouter(prefix="/sla-policies", tags=["SLA"], dependencies=[Depends(current_member)])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]


@router.get("", response_model=list[SlaPolicyRead])
def list_policies(sessions: Sessions):
    return sla.list_policies(sessions)


@router.patch("/{priority}", response_model=SlaPolicyRead, dependencies=[Depends(require_admin)])
def patch_policy(priority: Priority, payload: SlaPolicyPatch, sessions: Sessions):
    return sla.patch_policy(sessions, priority, payload)
