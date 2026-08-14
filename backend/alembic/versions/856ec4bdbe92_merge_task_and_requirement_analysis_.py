"""merge task and requirement analysis heads

Revision ID: 856ec4bdbe92
Revises: a6dee2fb05e9, d9d77d2f360f
Create Date: 2026-08-14 22:13:14.266964

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '856ec4bdbe92'
down_revision = ('a6dee2fb05e9', 'd9d77d2f360f')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass