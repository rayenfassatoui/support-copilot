from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_sessions
from app.integrations.openrouter import OpenRouterClient, get_openrouter
from app.schemas import KnowledgeCreate, KnowledgeRead, KnowledgeSummary
from app.services import knowledge

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]
Provider = Annotated[OpenRouterClient, Depends(get_openrouter)]


@router.post("", response_model=KnowledgeRead, status_code=201)
def create_document(payload: KnowledgeCreate, sessions: Sessions, provider: Provider):
    return knowledge.ingest(sessions, provider, payload)


@router.get("", response_model=list[KnowledgeSummary])
def list_documents(sessions: Sessions):
    return knowledge.list_documents(sessions)


@router.get("/{document_id}", response_model=KnowledgeRead)
def read_document(document_id: UUID, sessions: Sessions):
    return knowledge.read_document(sessions, document_id)
