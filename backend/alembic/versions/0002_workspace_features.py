"""Authenticated workspace, conversations, delivery, SLA and saved views."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_workspace_features"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("auth_subject", sa.String(200), unique=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'agent')", name="member_role"),
        sa.CheckConstraint("email = lower(email)", name="member_email_normalized"),
        sa.CheckConstraint("char_length(btrim(name)) BETWEEN 1 AND 200", name="member_name_length"),
        sa.CheckConstraint("version >= 1", name="member_version_positive"),
    )
    op.create_table("sla_policies",
        sa.Column("priority", sa.String(10), primary_key=True),
        sa.Column("first_response_minutes", sa.Integer(), nullable=False),
        sa.Column("resolution_minutes", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name="sla_priority"),
        sa.CheckConstraint("first_response_minutes BETWEEN 1 AND 525600", name="sla_response_positive"),
        sa.CheckConstraint("resolution_minutes BETWEEN first_response_minutes AND 525600", name="sla_resolution_positive"),
        sa.CheckConstraint("version >= 1", name="sla_version_positive"),
    )
    op.execute("INSERT INTO sla_policies VALUES ('urgent', 60, 240, 1), ('high', 240, 1440, 1), ('medium', 480, 2880, 1), ('low', 1440, 7200, 1)")
    op.add_column("tickets", sa.Column("priority", sa.String(10), nullable=False, server_default="medium"))
    op.add_column("tickets", sa.Column("first_response_due_at", sa.DateTime(timezone=True)))
    op.add_column("tickets", sa.Column("resolution_due_at", sa.DateTime(timezone=True)))
    op.add_column("tickets", sa.Column("first_response_at", sa.DateTime(timezone=True)))
    op.add_column("tickets", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE tickets SET first_response_due_at = created_at + interval '8 hours', resolution_due_at = created_at + interval '48 hours'")
    # Existing history contains the recorded completion time; do not invent a reply.
    op.execute("""UPDATE tickets SET resolved_at = COALESCE((
        SELECT max(e.created_at) FROM ticket_events e
        WHERE e.ticket_id = tickets.id AND e.changes->'status'->>'new' = 'resolved'
    ), updated_at) WHERE status = 'resolved'""")
    op.alter_column("tickets", "first_response_due_at", nullable=False)
    op.alter_column("tickets", "resolution_due_at", nullable=False)
    op.alter_column("tickets", "priority", server_default=None)
    op.create_check_constraint("ticket_priority", "tickets", "priority IN ('low', 'medium', 'high', 'urgent')")
    op.create_check_constraint("ticket_sla_deadline_order", "tickets", "resolution_due_at >= first_response_due_at")
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_resolution_due", "tickets", ["resolution_due_at"])
    op.add_column("ticket_events", sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("members.id", ondelete="RESTRICT")))
    op.create_table("ticket_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), sa.ForeignKey("copilot_runs.id", ondelete="RESTRICT")),
        sa.Column("ticket_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("delivery_status", sa.String(20), nullable=False),
        sa.Column("approved_by_id", sa.Uuid(), sa.ForeignKey("members.id", ondelete="RESTRICT")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("recipient_email", sa.String(320)),
        sa.Column("subject", sa.String(240)),
        sa.Column("smtp_message_id", sa.String(200), unique=True),
        sa.Column("delivery_error", sa.String(80)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('customer', 'note', 'reply')", name="message_kind"),
        sa.CheckConstraint("char_length(btrim(body)) BETWEEN 1 AND 10000", name="message_body_length"),
        sa.CheckConstraint("version >= 1 AND ticket_version >= 1", name="message_versions_positive"),
        sa.CheckConstraint("delivery_status IN ('not_applicable', 'draft', 'approved', 'sending', 'sent', 'failed', 'unknown')", name="message_delivery_status"),
        sa.CheckConstraint("(kind = 'reply' AND delivery_status != 'not_applicable') OR (kind != 'reply' AND delivery_status = 'not_applicable' AND source_run_id IS NULL)", name="message_kind_delivery"),
        sa.CheckConstraint("delivery_status NOT IN ('approved', 'sending', 'sent', 'failed', 'unknown') OR (approved_by_id IS NOT NULL AND approved_at IS NOT NULL AND recipient_email IS NOT NULL AND subject IS NOT NULL)", name="message_approval_required"),
        sa.CheckConstraint("(delivery_status = 'sent') = (sent_at IS NOT NULL)", name="message_sent_timestamp"),
    )
    op.create_index("ix_ticket_messages_ticket_time", "ticket_messages", ["ticket_id", "created_at", "id"])
    op.create_index("uq_ticket_open_reply_draft", "ticket_messages", ["ticket_id"], unique=True,
                    postgresql_where=sa.text("kind = 'reply' AND delivery_status = 'draft'"))
    op.create_table("saved_views",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "name", name="uq_saved_view_owner_name"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 60 AND name = btrim(name)", name="saved_view_name_length"),
        sa.CheckConstraint("jsonb_typeof(filters) = 'object'", name="saved_view_filters_object"),
        sa.CheckConstraint("version >= 1", name="saved_view_version_positive"),
    )


def downgrade() -> None:
    op.drop_table("saved_views")
    op.drop_table("ticket_messages")
    op.drop_column("ticket_events", "actor_id")
    op.drop_index("ix_tickets_resolution_due", table_name="tickets")
    op.drop_index("ix_tickets_priority", table_name="tickets")
    op.drop_constraint("ticket_sla_deadline_order", "tickets", type_="check")
    op.drop_constraint("ticket_priority", "tickets", type_="check")
    for column in ("resolved_at", "first_response_at", "resolution_due_at", "first_response_due_at", "priority"):
        op.drop_column("tickets", column)
    op.drop_table("sla_policies")
    op.drop_table("members")
