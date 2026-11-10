"""add run timestamps to ingestion runs and raw object ledger

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10

The 0001 migration created ingestion_runs / ingestion_errors /
raw_source_objects without created_at / updated_at, while the SQLAlchemy
models declare them. Aligned with a follow-up migration instead of mutating
0001 (history is already applied).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    for table in ("ingestion_runs", "ingestion_errors", "raw_source_objects"):
        op.add_column(
            table,
            sa.Column("created_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        )
        op.add_column(
            table,
            sa.Column("updated_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        )


def downgrade() -> None:
    for table in ("ingestion_runs", "ingestion_errors", "raw_source_objects"):
        op.drop_column(table, "updated_at")
        op.drop_column(table, "created_at")
