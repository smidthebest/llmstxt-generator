"""Add incremental change tracking fields

Revision ID: 006
Revises: 005
Create Date: 2026-02-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("canonical_url", sa.String(length=2048), nullable=True))
    op.add_column("pages", sa.Column("metadata_hash", sa.String(length=64), nullable=True))
    op.add_column("pages", sa.Column("headings_hash", sa.String(length=64), nullable=True))
    op.add_column("pages", sa.Column("text_hash", sa.String(length=64), nullable=True))
    op.add_column("pages", sa.Column("links_json", sa.JSON(), nullable=True))
    op.add_column("pages", sa.Column("etag", sa.String(length=512), nullable=True))
    op.add_column("pages", sa.Column("last_modified", sa.String(length=255), nullable=True))
    op.add_column("pages", sa.Column("http_status", sa.Integer(), nullable=True))
    op.add_column(
        "pages",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "pages",
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "pages",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "pages",
        sa.Column(
            "last_checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.execute(
        """
        UPDATE pages
        SET
          first_seen_at = COALESCE(created_at, now()),
          last_seen_at = COALESCE(updated_at, created_at, now()),
          last_checked_at = COALESCE(updated_at, created_at, now()),
          is_active = true
        """
    )

    op.create_index("uq_pages_site_url", "pages", ["site_id", "url"], unique=True)
    op.create_index("ix_pages_site_active", "pages", ["site_id", "is_active"])
    op.create_index("ix_pages_last_checked", "pages", ["site_id", "last_checked_at"])

    op.add_column(
        "crawl_jobs",
        sa.Column("pages_added", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_jobs",
        sa.Column("pages_updated", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_jobs",
        sa.Column("pages_removed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_jobs",
        sa.Column("pages_unchanged", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_jobs",
        sa.Column(
            "llms_regenerated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column("crawl_jobs", sa.Column("change_summary_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("crawl_jobs", "change_summary_json")
    op.drop_column("crawl_jobs", "llms_regenerated")
    op.drop_column("crawl_jobs", "pages_unchanged")
    op.drop_column("crawl_jobs", "pages_removed")
    op.drop_column("crawl_jobs", "pages_updated")
    op.drop_column("crawl_jobs", "pages_added")

    op.drop_index("ix_pages_last_checked", table_name="pages")
    op.drop_index("ix_pages_site_active", table_name="pages")
    op.drop_index("uq_pages_site_url", table_name="pages")

    op.drop_column("pages", "last_checked_at")
    op.drop_column("pages", "last_seen_at")
    op.drop_column("pages", "first_seen_at")
    op.drop_column("pages", "is_active")
    op.drop_column("pages", "http_status")
    op.drop_column("pages", "last_modified")
    op.drop_column("pages", "etag")
    op.drop_column("pages", "links_json")
    op.drop_column("pages", "text_hash")
    op.drop_column("pages", "headings_hash")
    op.drop_column("pages", "metadata_hash")
    op.drop_column("pages", "canonical_url")
