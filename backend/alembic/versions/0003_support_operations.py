"""Inbound mail, immutable knowledge revisions, business operations and customer feedback."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003_support_operations"
down_revision = "0002_workspace_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("family_id", sa.Uuid()))
    op.execute("UPDATE knowledge_documents SET family_id = id")
    op.alter_column("knowledge_documents", "family_id", nullable=False)
    op.add_column("knowledge_documents", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("knowledge_documents", sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.drop_constraint("knowledge_documents_content_sha256_key", "knowledge_documents", type_="unique")
    op.drop_constraint("document_content_length", "knowledge_documents", type_="check")
    op.create_check_constraint("document_content_length", "knowledge_documents", "char_length(content) BETWEEN 50 AND 500000")
    op.create_check_constraint("document_version_positive", "knowledge_documents", "version >= 1")
    op.create_unique_constraint("uq_knowledge_family_version", "knowledge_documents", ["family_id", "version"])
    op.create_index("uq_knowledge_current_family", "knowledge_documents", ["family_id"], unique=True, postgresql_where=sa.text("is_current"))
    op.create_index("uq_knowledge_current_hash", "knowledge_documents", ["content_sha256"], unique=True, postgresql_where=sa.text("is_current"))
    op.alter_column("ticket_messages", "author_id", nullable=True)
    op.alter_column("ticket_messages", "smtp_message_id", type_=sa.String(998), existing_type=sa.String(200))
    op.add_column("ticket_messages", sa.Column("sender_email", sa.String(320)))
    op.add_column("ticket_messages", sa.Column("in_reply_to", sa.String(998)))
    op.add_column("ticket_messages", sa.Column("references", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.create_check_constraint("message_actor_required", "ticket_messages", "author_id IS NOT NULL OR (kind = 'customer' AND sender_email IS NOT NULL)")
    op.create_check_constraint("message_references_array", "ticket_messages", 'jsonb_typeof("references") = \'array\'')
    op.create_table("mailbox_states",
        sa.Column("mailbox_key", sa.String(64), primary_key=True),
        sa.Column("uid_validity", sa.BigInteger(), nullable=False),
        sa.Column("last_uid", sa.BigInteger(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(80)),
        sa.CheckConstraint("uid_validity >= 0 AND last_uid >= 0", name="mailbox_uid_nonnegative"),
    )
    op.create_table("inbound_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mailbox_key", sa.String(64), nullable=False),
        sa.Column("uid_validity", sa.BigInteger(), nullable=False),
        sa.Column("uid", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.String(998)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.String(80)),
        sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id", ondelete="RESTRICT")),
        sa.Column("ticket_message_id", sa.Uuid(), sa.ForeignKey("ticket_messages.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_key", "uid_validity", "uid", name="uq_inbound_mailbox_uid"),
        sa.CheckConstraint("uid_validity > 0 AND uid > 0", name="receipt_uid_positive"),
        sa.CheckConstraint("status IN ('imported', 'ignored', 'failed')", name="receipt_status"),
    )
    op.create_index("ix_inbound_receipts_mailbox_time", "inbound_receipts", ["mailbox_key", "created_at", "id"])
    op.create_table("business_calendar",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("weekdays", pg.JSONB(), nullable=False),
        sa.Column("opens_minute", sa.Integer(), nullable=False),
        sa.Column("closes_minute", sa.Integer(), nullable=False),
        sa.Column("holidays", pg.JSONB(), nullable=False),
        sa.Column("alert_minutes", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="calendar_singleton"),
        sa.CheckConstraint("opens_minute >= 0 AND closes_minute <= 1440 AND opens_minute < closes_minute", name="calendar_hours"),
        sa.CheckConstraint("jsonb_typeof(weekdays) = 'array' AND jsonb_array_length(weekdays) BETWEEN 1 AND 7 AND weekdays <@ '[0,1,2,3,4,5,6]'::jsonb", name="calendar_weekdays"),
        sa.CheckConstraint("jsonb_typeof(holidays) = 'array'", name="calendar_holidays"),
        sa.CheckConstraint("alert_minutes BETWEEN 1 AND 10080 AND version >= 1", name="calendar_settings"),
    )
    op.execute("INSERT INTO business_calendar VALUES (1,false,'UTC','[0,1,2,3,4]',540,1020,'[]',30,1)")
    op.create_table("assignment_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(10)),
        sa.Column("customer_domain", sa.String(253)),
        sa.Column("subject_contains", sa.String(200)),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("char_length(btrim(name)) BETWEEN 1 AND 100", name="assignment_rule_name"),
        sa.CheckConstraint("priority IS NULL OR priority IN ('low', 'medium', 'high', 'urgent')", name="assignment_rule_priority"),
        sa.CheckConstraint("position >= 0 AND version >= 1", name="assignment_rule_order_version"),
    )
    op.create_index("ix_assignment_rules_order", "assignment_rules", ["position", "id"])
    op.create_table("customer_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("ticket_messages.id", ondelete="SET NULL")),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rating", sa.Integer()),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="feedback_rating_range"),
        sa.CheckConstraint("(rating IS NULL) = (submitted_at IS NULL)", name="feedback_submission"),
        sa.CheckConstraint("comment IS NULL OR (rating IS NOT NULL AND char_length(comment) <= 2000)", name="feedback_comment"),
        sa.CheckConstraint("expires_at > created_at", name="feedback_expiry"),
    )
    op.create_index("ix_customer_feedback_submitted", "customer_feedback", ["submitted_at"])
    op.create_index("ix_customer_feedback_created", "customer_feedback", ["created_at"])
    op.create_index("ix_customer_feedback_message_id", "customer_feedback", ["message_id"])
    op.create_index("ix_tickets_created", "tickets", ["created_at"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM knowledge_documents WHERE version > 1 OR char_length(content) > 20000) OR EXISTS (SELECT 1 FROM ticket_messages WHERE author_id IS NULL OR char_length(smtp_message_id) > 200)")):
        raise RuntimeError("This downgrade cannot preserve imported mail or knowledge revisions. Export and migrate that data before downgrading.")
    op.drop_index("ix_tickets_created", table_name="tickets")
    for table in ("customer_feedback", "assignment_rules", "business_calendar", "inbound_receipts", "mailbox_states"):
        op.drop_table(table)
    op.drop_constraint("message_actor_required", "ticket_messages", type_="check")
    op.drop_constraint("message_references_array", "ticket_messages", type_="check")
    for column in ("references", "in_reply_to", "sender_email"):
        op.drop_column("ticket_messages", column)
    op.alter_column("ticket_messages", "author_id", nullable=False)
    op.alter_column("ticket_messages", "smtp_message_id", type_=sa.String(200), existing_type=sa.String(998))
    op.drop_index("uq_knowledge_current_hash", table_name="knowledge_documents")
    op.drop_index("uq_knowledge_current_family", table_name="knowledge_documents")
    op.drop_constraint("uq_knowledge_family_version", "knowledge_documents", type_="unique")
    op.drop_constraint("document_version_positive", "knowledge_documents", type_="check")
    op.drop_constraint("document_content_length", "knowledge_documents", type_="check")
    op.create_check_constraint("document_content_length", "knowledge_documents", "char_length(content) BETWEEN 50 AND 20000")
    op.create_unique_constraint("knowledge_documents_content_sha256_key", "knowledge_documents", ["content_sha256"])
    for column in ("is_current", "version", "family_id"):
        op.drop_column("knowledge_documents", column)
