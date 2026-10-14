from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session, sessionmaker

from app.analytics_schemas import FeedbackLookup, FeedbackSubmit
from app.db import get_sessions
from app.services import feedback

router = APIRouter(prefix="/feedback", tags=["customer feedback"])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]


@router.post("/validate")
def validate(payload: FeedbackLookup, sessions: Sessions, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return feedback.validate_feedback(sessions, payload.token)


@router.post("/submit")
def submit(payload: FeedbackSubmit, sessions: Sessions, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return feedback.submit_feedback(sessions, payload)
