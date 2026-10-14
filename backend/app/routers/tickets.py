from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_sessions
from app.integrations.openrouter import OpenRouterClient, get_openrouter
from app.schemas import AnalyzeRequest, CopilotRunRead, Status, TicketCreate, TicketEventRead, TicketPage, TicketPatch, TicketRead
from app.services import copilot, tickets

router = APIRouter(prefix="/tickets", tags=["tickets"])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]


@router.post("", response_model=TicketRead, status_code=201)
def create_ticket(payload: TicketCreate, sessions: Sessions):
    return tickets.create_ticket(sessions, payload)


@router.get("", response_model=TicketPage)
def list_tickets(sessions: Sessions, status: Status | None = None, assignee_id: UUID | None = None,
                 limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return tickets.list_tickets(sessions, status.value if status else None, assignee_id, limit, offset)


@router.get("/{ticket_id}", response_model=TicketRead)
def read_ticket(ticket_id: UUID, sessions: Sessions):
    return tickets.read_ticket(sessions, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketRead)
def patch_ticket(ticket_id: UUID, payload: TicketPatch, sessions: Sessions):
    return tickets.patch_ticket(sessions, ticket_id, payload)


@router.get("/{ticket_id}/events", response_model=list[TicketEventRead])
def events(ticket_id: UUID, sessions: Sessions):
    return tickets.list_events(sessions, ticket_id)


@router.post("/{ticket_id}/analyze", response_model=CopilotRunRead, status_code=201)
def analyze_ticket(ticket_id: UUID, payload: AnalyzeRequest, sessions: Sessions,
                   provider: Annotated[OpenRouterClient, Depends(get_openrouter)]):
    return copilot.analyze_ticket(sessions, provider, ticket_id, payload.version)
