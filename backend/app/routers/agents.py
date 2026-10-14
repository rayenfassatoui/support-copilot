from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import current_member
from app.db import get_sessions
from app.models import Agent
from app.schemas import AgentRead

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(current_member)])


@router.get("", response_model=list[AgentRead])
def agents(sessions: sessionmaker[Session] = Depends(get_sessions)):
    with sessions() as session:
        return [AgentRead.model_validate(agent) for agent in session.scalars(select(Agent).order_by(Agent.name, Agent.id))]
