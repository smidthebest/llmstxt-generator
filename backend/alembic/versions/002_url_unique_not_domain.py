"""Make URL unique instead of domain, allowing multiple sites per domain

Revision ID: 002
Revises: 001
Create Date: 2026-02-17
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the unique constraint on domain
    op.drop_index("ix_sites_domain", table_name="sites")
    op.drop_constraint("sites_domain_key", table_name="sites", type_="unique")
    op.create_index("ix_sites_domain", "sites", ["domain"])

    # Add unique constraint + index on url
    op.create_index("ix_sites_url", "sites", ["url"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sites_url", table_name="sites")
    op.drop_index("ix_sites_domain", table_name="sites")
    op.create_index("ix_sites_domain", "sites", ["domain"], unique=True)
