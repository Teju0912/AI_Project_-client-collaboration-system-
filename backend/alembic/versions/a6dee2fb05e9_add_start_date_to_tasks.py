"""add start_date to tasks

Revision ID: a6dee2fb05e9
Revises: c9d2f4a6b8e1
Create Date: 2026-08-14 19:28:13.255078

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6dee2fb05e9'
down_revision = 'c9d2f4a6b8e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('start_date', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('tasks', 'start_date')