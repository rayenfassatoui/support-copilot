from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_sessions

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request, sessions: sessionmaker[Session] = Depends(get_sessions)):
    with sessions() as session:
        session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "ai_configured": bool(request.app.state.settings.openrouter_api_key.get_secret_value().strip()),
    }
