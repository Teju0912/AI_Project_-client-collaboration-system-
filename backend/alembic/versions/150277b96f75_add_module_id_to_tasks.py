"""add module_id to tasks

Revision ID: 150277b96f75
Revises: 18e7425acfb5
Create Date: 2026-08-12 21:00:05.394305

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '150277b96f75'
down_revision = '18e7425acfb5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('module_id', sa.UUID(), nullable=True))
    op.add_column('tasks', sa.Column('completed_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_tasks_module_id'), 'tasks', ['module_id'], unique=False)
    op.create_foreign_key(None, 'tasks', 'project_modules', ['module_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(None, 'tasks', type_='foreignkey')
    op.drop_index(op.f('ix_tasks_module_id'), table_name='tasks')
    op.drop_column('tasks', 'completed_at')
    op.drop_column('tasks', 'module_id')