"""set requirement_analyses.document_id to ON DELETE SET NULL

Revision ID: d9d77d2f360f
Revises: b4e6eca51d6f
Create Date: 2026-08-14 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd9d77d2f360f'
down_revision = 'b4e6eca51d6f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE requirement_analyses
        DROP CONSTRAINT IF EXISTS requirement_analyses_document_id_fkey;

        ALTER TABLE requirement_analyses
        ADD CONSTRAINT requirement_analyses_document_id_fkey
        FOREIGN KEY (document_id) REFERENCES documents(id)
        ON DELETE SET NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE requirement_analyses
        DROP CONSTRAINT IF EXISTS requirement_analyses_document_id_fkey;

        ALTER TABLE requirement_analyses
        ADD CONSTRAINT requirement_analyses_document_id_fkey
        FOREIGN KEY (document_id) REFERENCES documents(id);
        """
    )
