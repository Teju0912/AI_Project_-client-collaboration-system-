"""add project_modules table

Revision ID: 18e7425acfb5
Revises: b4e6eca51d6f
Create Date: 2026-08-12 13:52:32.689655

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '18e7425acfb5'
down_revision = 'b4e6eca51d6f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('project_modules',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('icon', sa.String(length=10), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_modules_project_id'), 'project_modules', ['project_id'], unique=False)
    # NOTE: intentionally NOT touching document_chunks.embedding here.
    # That column must stay VECTOR(768) for Gemini embeddings — an
    # autogenerate glitch tried to revert it to 384, which was removed.


def downgrade() -> None:
    op.drop_index(op.f('ix_project_modules_project_id'), table_name='project_modules')
    op.drop_table('project_modules')