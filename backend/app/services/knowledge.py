from bisect import bisect_right
import hashlib
from math import ceil
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.errors import DomainError
from app.integrations.openrouter import OpenRouterClient
from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas import KnowledgeCreate, KnowledgeRead, KnowledgeSummary, RetrievedChunk
from app.tokenization import EMBEDDING_TOKEN_LIMIT, get_tokenizer, token_count


def normalize_content(content: str) -> str:
    return content.replace("\r\n", "\n").strip()


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_content(content).encode("utf-8")).hexdigest()


def chunk_content(content: str, *, prefix: str = "document: ", overlap: int = 32) -> list[str]:
    offsets = get_tokenizer().encode(content, add_special_tokens=False).offsets
    if not offsets:
        return []
    ends = [end for _, end in offsets]
    chunks = []
    start = 0
    while start < len(content):
        first = bisect_right(ends, start)
        stop = min(first + 480, len(offsets))
        while True:
            end = len(content) if stop == len(offsets) else offsets[stop - 1][1]
            candidate = content[start:end]
            if candidate and token_count(prefix + candidate) <= EMBEDDING_TOKEN_LIMIT:
                break
            stop -= 1
            if stop <= first:
                raise DomainError("ai_input_too_long")
        chunks.append(candidate)
        if end == len(content):
            break
        next_start = offsets[max(first + 1, stop - overlap)][0] if overlap else end
        start = next_start if next_start > start else end
    return chunks


def ensure_embedding_model(session: Session, model: str) -> None:
    mismatch = session.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.embedding_model != model).limit(1))
    if mismatch is not None:
        raise DomainError("embedding_model_mismatch")


def document_fields(document: KnowledgeDocument, count: int) -> dict:
    return {"id": document.id, "title": document.title, "source_url": document.source_url,
            "created_at": document.created_at, "chunk_count": count, "family_id": document.family_id,
            "version": document.version, "is_current": document.is_current}


def ingest(sessions: sessionmaker[Session], provider: OpenRouterClient, payload: KnowledgeCreate,
           *, previous_id: UUID | None = None, version: int | None = None) -> KnowledgeRead:
    content = normalize_content(payload.content)
    digest = content_hash(content)
    model = provider.settings.openrouter_embedding_model
    with sessions() as session:
        ensure_embedding_model(session, model)
        if previous_id is not None:
            previous = session.get(KnowledgeDocument, previous_id)
            if previous is None:
                raise DomainError("not_found")
            if not previous.is_current or previous.version != version:
                raise DomainError("knowledge_conflict")
        duplicate = session.scalar(select(KnowledgeDocument.id).where(
            KnowledgeDocument.content_sha256 == digest, KnowledgeDocument.is_current.is_(True)))
        if duplicate is not None and duplicate != previous_id:
            raise DomainError("duplicate_document")
    chunks = chunk_content(content)
    vectors = provider.embed(["document: " + chunk for chunk in chunks])
    try:
        with sessions.begin() as session:
            ensure_embedding_model(session, model)
            document_id = uuid4()
            family_id, next_version = document_id, 1
            if previous_id is not None:
                previous = session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == previous_id).with_for_update())
                if previous is None or not previous.is_current or previous.version != version:
                    raise DomainError("knowledge_conflict")
                family_id, next_version = previous.family_id, previous.version + 1
                previous.is_current = False
                session.flush()
            document = KnowledgeDocument(id=document_id, family_id=family_id, version=next_version, is_current=True,
                title=payload.title, content=content, source_url=str(payload.source_url) if payload.source_url else None,
                content_sha256=digest, embedding_model=model)
            session.add(document)
            session.flush()
            session.add_all([KnowledgeChunk(document_id=document.id, chunk_index=index, content=text, embedding=vector)
                             for index, (text, vector) in enumerate(zip(chunks, vectors, strict=True))])
            session.flush()
            return KnowledgeRead(**document_fields(document, len(chunks)), content=document.content)
    except IntegrityError as error:
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_knowledge_current_hash":
            raise DomainError("duplicate_document") from None
        if constraint in {"uq_knowledge_current_family", "uq_knowledge_family_version"}:
            raise DomainError("knowledge_conflict") from None
        raise


def list_documents(sessions: sessionmaker[Session]) -> list[KnowledgeSummary]:
    with sessions() as session:
        rows = session.execute(select(KnowledgeDocument, func.count(KnowledgeChunk.id))
                               .outerjoin(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
                               .where(KnowledgeDocument.is_current.is_(True))
                               .group_by(KnowledgeDocument.id).order_by(KnowledgeDocument.title, KnowledgeDocument.id)).all()
        return [KnowledgeSummary(**document_fields(document, count)) for document, count in rows]


def read_document(sessions: sessionmaker[Session], document_id: UUID) -> KnowledgeRead:
    with sessions() as session:
        document = session.get(KnowledgeDocument, document_id)
        if document is None:
            raise DomainError("not_found")
        count = session.scalar(select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
        return KnowledgeRead(**document_fields(document, count), content=document.content)


def document_history(sessions: sessionmaker[Session], document_id: UUID, limit: int, offset: int) -> list[KnowledgeSummary]:
    with sessions() as session:
        document = session.get(KnowledgeDocument, document_id)
        if document is None:
            raise DomainError("not_found")
        rows = session.execute(select(KnowledgeDocument, func.count(KnowledgeChunk.id))
            .outerjoin(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.family_id == document.family_id).group_by(KnowledgeDocument.id)
            .order_by(KnowledgeDocument.version.desc()).limit(limit).offset(offset)).all()
        return [KnowledgeSummary(**document_fields(row, count)) for row, count in rows]


def retrieve(sessions: sessionmaker[Session], provider: OpenRouterClient, query: str) -> list[RetrievedChunk]:
    model = provider.settings.openrouter_embedding_model
    with sessions() as session:
        ensure_embedding_model(session, model)
        if session.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.is_current.is_(True)).limit(1)) is None:
            return []
    segments = chunk_content(query, prefix="query: ", overlap=0)
    vectors = provider.embed(["query: " + segment for segment in segments])
    # Every segment contributes; at most eight chronological centroids plus the latest request.
    width = max(1, ceil(len(vectors) / 8))
    searches = []
    for start in range(0, len(vectors), width):
        group = vectors[start:start + width]
        centroid = [sum(values) / len(group) for values in zip(*group, strict=True)]
        searches.extend([centroid] if any(centroid) else group)
    if len(vectors) > 1:
        searches.append(vectors[-1])
    ranked: dict[UUID, tuple[RetrievedChunk, float]] = {}
    with sessions() as session:
        ensure_embedding_model(session, model)
        for vector in searches:
            rows = session.execute(select(KnowledgeChunk, KnowledgeDocument)
                .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                .where(KnowledgeDocument.embedding_model == model, KnowledgeDocument.is_current.is_(True))
                .order_by(KnowledgeChunk.embedding.cosine_distance(vector), KnowledgeChunk.id).limit(5)).all()
            for rank, (chunk, document) in enumerate(rows, start=1):
                value = RetrievedChunk(id=chunk.id, document_id=document.id, title=document.title,
                    text=chunk.content, source_url=document.source_url)
                ranked[chunk.id] = (value, ranked.get(chunk.id, (value, 0))[1] + 1 / (60 + rank))
    return [item[0] for item in sorted(ranked.values(), key=lambda item: (-item[1], str(item[0].id)))[:5]]
