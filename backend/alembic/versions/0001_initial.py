"""Initial support copilot schema including pgvector."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import VECTOR

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("agents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.CheckConstraint("char_length(btrim(name)) BETWEEN 1 AND 200", name="agent_name_length"),
    )
    op.create_table("tickets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("customer_email", sa.String(320), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="RESTRICT")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("char_length(title) BETWEEN 3 AND 200 AND title = btrim(title)", name="ticket_title_length"),
        sa.CheckConstraint("char_length(description) BETWEEN 10 AND 10000 AND description = btrim(description)", name="ticket_description_length"),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'resolved', 'escalated')", name="ticket_status"),
        sa.CheckConstraint("version >= 1", name="ticket_version_positive"),
    )
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_assignee_id", "tickets", ["assignee_id"])
    op.create_index("ix_tickets_updated_id", "tickets", ["updated_at", "id"])
    op.create_table("ticket_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ticket_version", sa.Integer(), nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ticket_version >= 1", name="event_version_positive"),
        sa.CheckConstraint("jsonb_typeof(changes) = 'object'", name="event_changes_object"),
    )
    op.create_index("ix_ticket_events_ticket_time", "ticket_events", ["ticket_id", "created_at", "id"])
    op.create_table("knowledge_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("embedding_model", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("char_length(title) BETWEEN 3 AND 200 AND title = btrim(title)", name="document_title_length"),
        sa.CheckConstraint("char_length(content) BETWEEN 50 AND 20000", name="document_content_length"),
        sa.CheckConstraint("source_url IS NULL OR source_url ~ '^https?://'", name="document_source_http"),
    )
    op.create_table("knowledge_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("knowledge_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", VECTOR(1024), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        sa.CheckConstraint("chunk_index >= 0", name="chunk_index_nonnegative"),
        sa.CheckConstraint("char_length(content) > 0", name="chunk_nonempty"),
    )
    op.create_index("ix_knowledge_chunks_document", "knowledge_chunks", ["document_id"])
    op.create_table("copilot_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ticket_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(512), nullable=False),
        sa.Column("intent", sa.String(20), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("classification_reason", sa.String(500), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("response_draft", sa.Text()),
        sa.Column("escalation_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ticket_version >= 1", name="run_version_positive"),
        sa.CheckConstraint("intent IN ('billing', 'technical', 'account', 'cancellation', 'security', 'other')", name="run_intent"),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name="run_priority"),
        sa.CheckConstraint("char_length(btrim(classification_reason)) BETWEEN 1 AND 500", name="run_reason_length"),
        sa.CheckConstraint("(grounded AND response_draft IS NOT NULL AND char_length(btrim(response_draft)) BETWEEN 1 AND 6000) OR (NOT grounded AND response_draft IS NULL)", name="run_grounding_draft"),
        sa.CheckConstraint("jsonb_typeof(escalation_reasons) = 'array' AND escalation_reasons <@ '[\"insufficient_knowledge\",\"security_or_privacy\",\"legal_or_compliance\",\"human_requested\",\"urgent_impact\",\"policy_requires_review\"]'::jsonb", name="run_escalation_values"),
    )
    op.create_index("ix_copilot_runs_ticket_time", "copilot_runs", ["ticket_id", "created_at", "id"])
    op.create_table("copilot_citations",
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("copilot_runs.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("chunk_id", sa.Uuid(), sa.ForeignKey("knowledge_chunks.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("quote", sa.String(600), nullable=False),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_run_citation_ordinal"),
        sa.CheckConstraint("ordinal > 0", name="citation_ordinal_positive"),
        sa.CheckConstraint("char_length(btrim(quote)) BETWEEN 1 AND 600", name="citation_quote_length"),
    )


def downgrade() -> None:
    # Do not remove the database-managed vector extension.
    for table in ("copilot_citations", "copilot_runs", "knowledge_chunks", "knowledge_documents", "ticket_events", "tickets", "agents"):
        op.drop_table(table)
