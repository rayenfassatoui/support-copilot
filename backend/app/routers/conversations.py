from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, sessionmaker

from app.auth import current_member
from app.db import get_sessions
from app.integrations.mail import SMTPMailer, get_mailer
from app.schemas import MemberRead, MessageAction, MessageCreate, MessagePatch, MessageRead
from app.services import conversations

router = APIRouter(prefix="/tickets/{ticket_id}/messages", tags=["conversations"])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]
Actor = Annotated[MemberRead, Depends(current_member)]


@router.get("", response_model=list[MessageRead])
def list_messages(ticket_id: UUID, sessions: Sessions, actor: Actor):
    return conversations.list_messages(sessions, ticket_id)


@router.post("", response_model=MessageRead, status_code=201)
def create_message(ticket_id: UUID, payload: MessageCreate, sessions: Sessions, actor: Actor):
    return conversations.create_message(sessions, ticket_id, payload, actor)


@router.patch("/{message_id}", response_model=MessageRead)
def patch_message(ticket_id: UUID, message_id: UUID, payload: MessagePatch, sessions: Sessions, actor: Actor):
    return conversations.patch_message(sessions, ticket_id, message_id, payload, actor)


@router.post("/{message_id}/approve", response_model=MessageRead)
def approve_message(ticket_id: UUID, message_id: UUID, payload: MessageAction, sessions: Sessions, actor: Actor):
    return conversations.approve_message(sessions, ticket_id, message_id, payload, actor)


@router.post("/{message_id}/send", response_model=MessageRead)
def send_message(ticket_id: UUID, message_id: UUID, payload: MessageAction, sessions: Sessions, actor: Actor,
                 mailer: Annotated[SMTPMailer, Depends(get_mailer)]):
    return conversations.send_message(sessions, ticket_id, message_id, payload, actor, mailer)
