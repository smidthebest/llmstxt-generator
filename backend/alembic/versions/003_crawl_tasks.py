"""Add durable crawl task queue

Revision ID: 003
Revises: 002
Create Date: 2026-02-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crawl_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("crawl_job_id", sa.Integer(), sa.ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_crawl_tasks_site_id", "crawl_tasks", ["site_id"])
    op.create_index("ix_crawl_tasks_crawl_job_id", "crawl_tasks", ["crawl_job_id"])
    op.create_index(
        "ix_crawl_tasks_claim",
        "crawl_tasks",
        ["status", "available_at", "priority", "created_at"],
    )
    op.create_index("ix_crawl_tasks_lease", "crawl_tasks", ["lease_owner", "leased_until"])
    op.create_index(
        "uq_crawl_tasks_idempotency_key",
        "crawl_tasks",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_crawl_tasks_idempotency_key", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_lease", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_claim", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_crawl_job_id", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_site_id", table_name="crawl_tasks")
    op.drop_table("crawl_tasks")
