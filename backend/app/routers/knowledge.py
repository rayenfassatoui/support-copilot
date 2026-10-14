from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session, sessionmaker

from app.auth import current_member, require_admin
from app.db import get_sessions
from app.integrations.openrouter import OpenRouterClient, get_openrouter
from app.errors import DomainError
from app.knowledge_import import MAX_BYTES, import_source
from app.knowledge_schemas import KnowledgeUpdate, URLImport
from app.schemas import KnowledgeCreate, KnowledgeRead, KnowledgeSummary, Title
from app.services import knowledge

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(current_member)])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]
Provider = Annotated[OpenRouterClient, Depends(get_openrouter)]


@router.post("", response_model=KnowledgeRead, status_code=201, dependencies=[Depends(require_admin)])
def create_document(payload: KnowledgeCreate, sessions: Sessions, provider: Provider):
    return knowledge.ingest(sessions, provider, payload)


@router.get("", response_model=list[KnowledgeSummary])
def list_documents(sessions: Sessions):
    return knowledge.list_documents(sessions)


@router.post("/import/url", response_model=KnowledgeRead, status_code=201, dependencies=[Depends(require_admin)])
def import_url(payload: URLImport, sessions: Sessions, provider: Provider):
    content, source_url = import_source(str(payload.url))
    return knowledge.ingest(sessions, provider, KnowledgeCreate(title=payload.title, content=content, source_url=source_url))


@router.post("/import/file", response_model=KnowledgeRead, status_code=201, dependencies=[Depends(require_admin)])
def import_file(sessions: Sessions, provider: Provider, file: Annotated[UploadFile, File()],
                title: Annotated[Title, Form()]):
    name = (file.filename or "").lower()
    if not name.endswith((".pdf", ".txt", ".md")):
        raise DomainError("knowledge_import_unsupported")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise DomainError("knowledge_import_too_large")
    content, _ = import_source(data, "application/pdf" if name.endswith(".pdf") else "text/plain")
    return knowledge.ingest(sessions, provider, KnowledgeCreate(title=title, content=content))


@router.put("/{document_id}", response_model=KnowledgeRead, dependencies=[Depends(require_admin)])
def update_document(document_id: UUID, payload: KnowledgeUpdate, sessions: Sessions, provider: Provider):
    return knowledge.ingest(sessions, provider, KnowledgeCreate(**payload.model_dump(exclude={"version"})),
                            previous_id=document_id, version=payload.version)


@router.get("/{document_id}/history", response_model=list[KnowledgeSummary])
def history(document_id: UUID, sessions: Sessions, limit: Annotated[int, Query(ge=1, le=100)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0):
    return knowledge.document_history(sessions, document_id, limit, offset)


@router.get("/{document_id}", response_model=KnowledgeRead)
def read_document(document_id: UUID, sessions: Sessions):
    return knowledge.read_document(sessions, document_id)
