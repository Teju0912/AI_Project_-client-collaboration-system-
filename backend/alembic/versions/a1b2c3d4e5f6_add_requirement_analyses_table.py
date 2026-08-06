"""add requirement_analyses table

Revision ID: a1b2c3d4e5f6
Revises: df53432df1b2
Create Date: 2026-08-04 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'df53432df1b2'
branch_labels = None
depends_on = None


def upgrade():
    # Add epic column to tasks table
    op.add_column('tasks', sa.Column('epic', sa.String(length=255), nullable=True))

    # Create requirement_analyses table
    op.create_table(
        'requirement_analyses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('raw_output', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending_review'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    # Index on organization_id for faster multi-tenant queries
    op.create_index(op.f('ix_requirement_analyses_organization_id'), 'requirement_analyses', ['organization_id'], unique=False)


def downgrade():
    # Drop table and column
    op.drop_index(op.f('ix_requirement_analyses_organization_id'), table_name='requirement_analyses')
    op.drop_table('requirement_analyses')
    op.drop_column('tasks', 'epic')
