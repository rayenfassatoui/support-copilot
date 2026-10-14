from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.auth import current_member, require_admin
from app.db import get_sessions
from app.schemas import MemberCreate, MemberPatch, MemberRead
from app.services import members

router = APIRouter(tags=["authentication"])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]
Admin = Annotated[MemberRead, Depends(require_admin)]


@router.get("/auth/config")
def auth_config(request: Request) -> dict:
    base = request.app.state.settings.neon_auth_base_url
    return {"auth_url": base or None, "configured": bool(base)}


@router.get("/auth/me", response_model=MemberRead)
def me(member: Annotated[MemberRead, Depends(current_member)]):
    return member


@router.get("/members", response_model=list[MemberRead])
def list_members(sessions: Sessions, admin: Admin):
    return members.list_members(sessions)


@router.post("/members", response_model=MemberRead, status_code=201)
def create_member(payload: MemberCreate, sessions: Sessions, admin: Admin):
    return members.create_member(sessions, payload)


@router.patch("/members/{member_id}", response_model=MemberRead)
def patch_member(member_id: UUID, payload: MemberPatch, sessions: Sessions, admin: Admin):
    return members.patch_member(sessions, member_id, payload)


@router.get("/delivery/config")
def delivery_config(request: Request, member: Annotated[MemberRead, Depends(current_member)]) -> dict:
    settings = request.app.state.settings
    return {
        "configured": bool(settings.smtp_host),
        "mode": settings.mail_delivery_mode,
        "mailpit_url": "http://127.0.0.1:8025" if settings.mail_delivery_mode == "mailpit" else None,
    }
