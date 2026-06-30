"""add interview_cache table

Revision ID: 0002_add_interview_cache
Revises: 0001_add_analysis_cache
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_add_interview_cache"
down_revision = "0001_add_analysis_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_cache",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False, server_default="v2"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("prediction_result", JSONB, nullable=True),
        if_not_exists=True,
    )
    op.create_index("ix_interview_cache_trace_id", "interview_cache", ["trace_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_interview_cache_trace_id", table_name="interview_cache")
    op.drop_table("interview_cache")
