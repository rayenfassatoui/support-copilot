from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth import current_member
from app.db import get_sessions
from app.integrations.openrouter import OpenRouterClient, get_openrouter
from app.schemas import AnalyzeRequest, CopilotRunRead, MemberRead, TicketCreate, TicketEventRead, TicketPage, TicketPatch, TicketRead, TicketSearch
from app.services import copilot, tickets

router = APIRouter(prefix="/tickets", tags=["tickets"], dependencies=[Depends(current_member)])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]
Actor = Annotated[MemberRead, Depends(current_member)]


@router.post("", response_model=TicketRead, status_code=201)
def create_ticket(payload: TicketCreate, sessions: Sessions, actor: Actor):
    return tickets.create_ticket(sessions, payload, actor)


@router.get("", response_model=TicketPage)
def list_tickets(sessions: Sessions, actor: Actor, query: Annotated[TicketSearch, Query()]):
    return tickets.list_tickets(sessions, query, actor)


@router.get("/{ticket_id}", response_model=TicketRead)
def read_ticket(ticket_id: UUID, sessions: Sessions):
    return tickets.read_ticket(sessions, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketRead)
def patch_ticket(ticket_id: UUID, payload: TicketPatch, sessions: Sessions, actor: Actor):
    return tickets.patch_ticket(sessions, ticket_id, payload, actor)


@router.get("/{ticket_id}/events", response_model=list[TicketEventRead])
def events(ticket_id: UUID, sessions: Sessions):
    return tickets.list_events(sessions, ticket_id)


@router.post("/{ticket_id}/analyze", response_model=CopilotRunRead, status_code=201)
def analyze_ticket(ticket_id: UUID, payload: AnalyzeRequest, sessions: Sessions,
                   provider: Annotated[OpenRouterClient, Depends(get_openrouter)]):
    return copilot.analyze_ticket(sessions, provider, ticket_id, payload.version)
