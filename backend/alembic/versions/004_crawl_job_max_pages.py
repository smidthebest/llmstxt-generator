"""Add max_pages column to crawl_jobs

Revision ID: 004
Revises: 003
Create Date: 2026-02-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crawl_jobs",
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="200"),
    )


def downgrade() -> None:
    op.drop_column("crawl_jobs", "max_pages")
