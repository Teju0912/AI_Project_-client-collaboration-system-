"""fix_embedding_column_jsonb_to_vector

Revision ID: df53432df1b2
Revises: bb0c2f679323
Create Date: 2026-08-03 15:59:59.937127

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'df53432df1b2'
down_revision = 'bb0c2f679323'
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass