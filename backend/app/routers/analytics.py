from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from app.analytics_schemas import AnalyticsRead, FeedbackRequest
from app.auth import current_member
from app.db import get_sessions
from app.schemas import MemberRead, MessageRead
from app.services import analytics, feedback

router = APIRouter(tags=["analytics"])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]
Actor = Annotated[MemberRead, Depends(current_member)]


@router.get("/analytics", response_model=AnalyticsRead)
def report(sessions: Sessions, actor: Actor, start: date | None = None, end: date | None = None):
    end = end or datetime.now(timezone.utc).date() + timedelta(days=1)
    start = start or end - timedelta(days=30)
    if not 1 <= (end - start).days <= 366:
        raise HTTPException(422, detail={"code": "invalid_date_range", "message": "Select a range of 1 to 366 days; the end date is exclusive."})
    return analytics.report(sessions, start, end)


@router.get("/tickets/{ticket_id}/feedback")
def status(ticket_id: UUID, sessions: Sessions, actor: Actor):
    return feedback.feedback_status(sessions, ticket_id)


@router.post("/tickets/{ticket_id}/feedback/request", response_model=MessageRead, status_code=201)
def request_feedback(ticket_id: UUID, payload: FeedbackRequest, request: Request, sessions: Sessions, actor: Actor):
    return feedback.request_feedback(sessions, request.app.state.settings, ticket_id, payload, actor)
