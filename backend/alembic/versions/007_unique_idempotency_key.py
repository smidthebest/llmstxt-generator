"""Add unique constraint on crawl_tasks.idempotency_key

Revision ID: 007
Revises: 006
Create Date: 2026-02-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Check if index already exists (e.g. created by metadata.create_all)
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'uq_crawl_tasks_idempotency_key'"
    ))
    if result.scalar():
        return

    # Deduplicate any existing rows first (keep lowest id per key)
    op.execute("""
        DELETE FROM crawl_tasks
        WHERE id NOT IN (
            SELECT MIN(id) FROM crawl_tasks
            WHERE idempotency_key IS NOT NULL
            GROUP BY idempotency_key
        )
        AND idempotency_key IS NOT NULL
    """)
    op.create_index(
        "uq_crawl_tasks_idempotency_key",
        "crawl_tasks",
        ["idempotency_key"],
        unique=True,
        postgresql_where="idempotency_key IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_crawl_tasks_idempotency_key", table_name="crawl_tasks")
