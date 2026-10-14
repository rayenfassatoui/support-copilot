from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    __table_args__ = (CheckConstraint("char_length(btrim(name)) BETWEEN 1 AND 200", name="agent_name_length"),)


class Member(Base):
    __tablename__ = "members"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    auth_subject: Mapped[str | None] = mapped_column(String(200), unique=True)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'agent')", name="member_role"),
        CheckConstraint("email = lower(email)", name="member_email_normalized"),
        CheckConstraint("char_length(btrim(name)) BETWEEN 1 AND 200", name="member_name_length"),
        CheckConstraint("version >= 1", name="member_version_positive"),
    )


class SlaPolicy(Base):
    __tablename__ = "sla_policies"
    priority: Mapped[str] = mapped_column(String(10), primary_key=True)
    first_response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name="sla_priority"),
        CheckConstraint("first_response_minutes BETWEEN 1 AND 525600", name="sla_response_positive"),
        CheckConstraint("resolution_minutes BETWEEN first_response_minutes AND 525600", name="sla_resolution_positive"),
        CheckConstraint("version >= 1", name="sla_version_positive"),
    )


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    first_response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolution_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 3 AND 200 AND title = btrim(title)", name="ticket_title_length"),
        CheckConstraint("char_length(description) BETWEEN 10 AND 10000 AND description = btrim(description)", name="ticket_description_length"),
        CheckConstraint("status IN ('open', 'in_progress', 'resolved', 'escalated')", name="ticket_status"),
        CheckConstraint("version >= 1", name="ticket_version_positive"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name="ticket_priority"),
        CheckConstraint("resolution_due_at >= first_response_due_at", name="ticket_sla_deadline_order"),
        Index("ix_tickets_priority", "priority"),
        Index("ix_tickets_resolution_due", "resolution_due_at"),
        Index("ix_tickets_status", "status"), Index("ix_tickets_assignee_id", "assignee_id"),
        Index("ix_tickets_updated_id", "updated_at", "id"),
    )


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False)
    ticket_version: Mapped[int] = mapped_column(Integer, nullable=False)
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("ticket_version >= 1", name="event_version_positive"),
        CheckConstraint("jsonb_typeof(changes) = 'object'", name="event_changes_object"),
        Index("ix_ticket_events_ticket_time", "ticket_id", "created_at", "id"),
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    embedding_model: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 3 AND 200 AND title = btrim(title)", name="document_title_length"),
        CheckConstraint("char_length(content) BETWEEN 50 AND 20000", name="document_content_length"),
        CheckConstraint("source_url IS NULL OR source_url ~ '^https?://'", name="document_source_http"),
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="RESTRICT"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(1024), nullable=False)
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_nonnegative"),
        CheckConstraint("char_length(content) > 0", name="chunk_nonempty"),
        Index("ix_knowledge_chunks_document", "document_id"),
    )


class CopilotRun(Base):
    __tablename__ = "copilot_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False)
    ticket_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(512), nullable=False)
    intent: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    classification_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_draft: Mapped[str | None] = mapped_column(Text)
    escalation_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("ticket_version >= 1", name="run_version_positive"),
        CheckConstraint("intent IN ('billing', 'technical', 'account', 'cancellation', 'security', 'other')", name="run_intent"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name="run_priority"),
        CheckConstraint("char_length(btrim(classification_reason)) BETWEEN 1 AND 500", name="run_reason_length"),
        CheckConstraint("(grounded AND response_draft IS NOT NULL AND char_length(btrim(response_draft)) BETWEEN 1 AND 6000) OR (NOT grounded AND response_draft IS NULL)", name="run_grounding_draft"),
        CheckConstraint("jsonb_typeof(escalation_reasons) = 'array' AND escalation_reasons <@ '[\"insufficient_knowledge\",\"security_or_privacy\",\"legal_or_compliance\",\"human_requested\",\"urgent_impact\",\"policy_requires_review\"]'::jsonb", name="run_escalation_values"),
        Index("ix_copilot_runs_ticket_time", "ticket_id", "created_at", "id"),
    )


class CopilotCitation(Base):
    __tablename__ = "copilot_citations"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("copilot_runs.id", ondelete="RESTRICT"), primary_key=True)
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="RESTRICT"), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str] = mapped_column(String(600), nullable=False)
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_run_citation_ordinal"),
        CheckConstraint("ordinal > 0", name="citation_ordinal_positive"),
        CheckConstraint("char_length(btrim(quote)) BETWEEN 1 AND 600", name="citation_quote_length"),
    )


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    source_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("copilot_runs.id", ondelete="RESTRICT"))
    ticket_version: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False)
    approved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recipient_email: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(240))
    smtp_message_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    delivery_error: Mapped[str | None] = mapped_column(String(80))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("kind IN ('customer', 'note', 'reply')", name="message_kind"),
        CheckConstraint("char_length(btrim(body)) BETWEEN 1 AND 10000", name="message_body_length"),
        CheckConstraint("version >= 1 AND ticket_version >= 1", name="message_versions_positive"),
        CheckConstraint("delivery_status IN ('not_applicable', 'draft', 'approved', 'sending', 'sent', 'failed', 'unknown')", name="message_delivery_status"),
        CheckConstraint("(kind = 'reply' AND delivery_status != 'not_applicable') OR (kind != 'reply' AND delivery_status = 'not_applicable' AND source_run_id IS NULL)", name="message_kind_delivery"),
        CheckConstraint("delivery_status NOT IN ('approved', 'sending', 'sent', 'failed', 'unknown') OR (approved_by_id IS NOT NULL AND approved_at IS NOT NULL AND recipient_email IS NOT NULL AND subject IS NOT NULL)", name="message_approval_required"),
        CheckConstraint("(delivery_status = 'sent') = (sent_at IS NOT NULL)", name="message_sent_timestamp"),
        Index("ix_ticket_messages_ticket_time", "ticket_id", "created_at", "id"),
        Index("uq_ticket_open_reply_draft", "ticket_id", unique=True, postgresql_where=text("kind = 'reply' AND delivery_status = 'draft'")),
    )


class SavedView(Base):
    __tablename__ = "saved_views"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_saved_view_owner_name"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 60 AND name = btrim(name)", name="saved_view_name_length"),
        CheckConstraint("jsonb_typeof(filters) = 'object'", name="saved_view_filters_object"),
        CheckConstraint("version >= 1", name="saved_view_version_positive"),
    )
