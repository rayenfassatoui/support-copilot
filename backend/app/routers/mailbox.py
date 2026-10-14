from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.auth import require_admin
from app.db import get_sessions
from app.schemas import MemberRead
from app.services import mailbox

router = APIRouter(prefix="/mailbox", tags=["mailbox"])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]
Admin = Annotated[MemberRead, Depends(require_admin)]


@router.get("")
def status(request: Request, sessions: Sessions, admin: Admin):
    return mailbox.status(sessions, request.app.state.settings)


@router.post("/sync")
def sync(request: Request, sessions: Sessions, admin: Admin):
    return mailbox.sync_mailbox(sessions, request.app.state.settings)
