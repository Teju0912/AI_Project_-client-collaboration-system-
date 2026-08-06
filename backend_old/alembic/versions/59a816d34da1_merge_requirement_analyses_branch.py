"""merge requirement_analyses branch

Revision ID: 59a816d34da1
Revises: 63d4be79a70f, a1b2c3d4e5f6
Create Date: 2026-08-04 22:13:46.475727

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '59a816d34da1'
down_revision = ('63d4be79a70f', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass