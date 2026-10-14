import hashlib
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.errors import DomainError
from app.integrations.openrouter import OpenRouterClient
from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas import KnowledgeCreate, KnowledgeRead, KnowledgeSummary, RetrievedChunk


def normalize_content(content: str) -> str:
    return content.replace("\r\n", "\n").strip()


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_content(content).encode("utf-8")).hexdigest()


def chunk_content(content: str) -> list[str]:
    chunks = []
    for start in range(0, len(content), 850):
        end = min(start + 1000, len(content))
        chunks.append(content[start:end])
        if end == len(content):
            break
    return chunks


def ensure_embedding_model(session: Session, model: str) -> None:
    mismatch = session.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.embedding_model != model).limit(1))
    if mismatch is not None:
        raise DomainError("embedding_model_mismatch")


def document_fields(document: KnowledgeDocument, count: int) -> dict:
    return {"id": document.id, "title": document.title, "source_url": document.source_url,
            "created_at": document.created_at, "chunk_count": count}


def ingest(sessions: sessionmaker[Session], provider: OpenRouterClient, payload: KnowledgeCreate) -> KnowledgeRead:
    content = normalize_content(payload.content)
    digest = content_hash(content)
    model = provider.settings.openrouter_embedding_model
    with sessions() as session:
        ensure_embedding_model(session, model)
        if session.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.content_sha256 == digest)) is not None:
            raise DomainError("duplicate_document")
    chunks = chunk_content(content)
    vectors = provider.embed(["document: " + chunk for chunk in chunks])
    try:
        with sessions.begin() as session:
            ensure_embedding_model(session, model)
            document = KnowledgeDocument(title=payload.title, content=content,
                                         source_url=str(payload.source_url) if payload.source_url else None,
                                         content_sha256=digest, embedding_model=model)
            session.add(document)
            session.flush()
            session.add_all([KnowledgeChunk(document_id=document.id, chunk_index=index, content=text, embedding=vector)
                             for index, (text, vector) in enumerate(zip(chunks, vectors, strict=True))])
            session.flush()
            return KnowledgeRead(**document_fields(document, len(chunks)), content=document.content)
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23505" and getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "knowledge_documents_content_sha256_key":
            raise DomainError("duplicate_document") from None
        raise


def list_documents(sessions: sessionmaker[Session]) -> list[KnowledgeSummary]:
    with sessions() as session:
        rows = session.execute(select(KnowledgeDocument, func.count(KnowledgeChunk.id))
                               .outerjoin(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
                               .group_by(KnowledgeDocument.id).order_by(KnowledgeDocument.title, KnowledgeDocument.id)).all()
        return [KnowledgeSummary(**document_fields(document, count)) for document, count in rows]


def read_document(sessions: sessionmaker[Session], document_id: UUID) -> KnowledgeRead:
    with sessions() as session:
        document = session.get(KnowledgeDocument, document_id)
        if document is None:
            raise DomainError("not_found")
        count = session.scalar(select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
        return KnowledgeRead(**document_fields(document, count), content=document.content)


def retrieve(sessions: sessionmaker[Session], provider: OpenRouterClient, query: str) -> list[RetrievedChunk]:
    model = provider.settings.openrouter_embedding_model
    with sessions() as session:
        ensure_embedding_model(session, model)
        if session.scalar(select(KnowledgeDocument.id).limit(1)) is None:
            return []
    vector = provider.embed(["query: " + query])[0]
    with sessions() as session:
        ensure_embedding_model(session, model)
        rows = session.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.embedding_model == model)
            .order_by(KnowledgeChunk.embedding.cosine_distance(vector), KnowledgeChunk.id).limit(5)
        ).all()
        return [RetrievedChunk(id=chunk.id, document_id=document.id, title=document.title,
                               text=chunk.content, source_url=document.source_url) for chunk, document in rows]
