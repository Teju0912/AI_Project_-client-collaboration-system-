"""change embedding dimension 384 to 768 for gemini
Revision ID: b4e6eca51d6f
Revises: c91c743b9486
Create Date: 2026-08-12 00:46:24.760177
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4e6eca51d6f'
down_revision = 'c91c743b9486'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # document_chunks was empty when this migration was written, so no
    # data-preserving cast is needed — just drop and recreate the column
    # at the new dimension. USING NULL clears any stale 384-dim rows so
    # the type change is always safe to run.
    op.execute(
        "ALTER TABLE document_chunks "
        "ALTER COLUMN embedding TYPE vector(768) USING NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE document_chunks "
        "ALTER COLUMN embedding TYPE vector(384) USING NULL"
    )