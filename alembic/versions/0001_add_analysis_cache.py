"""add analysis_cache table

Revision ID: 0001_add_analysis_cache
Revises:
Create Date: 2026-06-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_add_analysis_cache"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_cache",
        sa.Column("trace_id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("resume_name", sa.String(length=200), nullable=True),
        sa.Column("job_title", sa.String(length=200), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("resume_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("job_requirement", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("match_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("suggestions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_analysis_cache_created_at", "analysis_cache", ["created_at"]
    )
    op.create_index(
        "ix_analysis_cache_job_title", "analysis_cache", ["job_title"]
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_cache_job_title", table_name="analysis_cache")
    op.drop_index("ix_analysis_cache_created_at", table_name="analysis_cache")
    op.drop_table("analysis_cache")
