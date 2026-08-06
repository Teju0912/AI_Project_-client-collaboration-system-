"""add document_chunks table for RAG

Revision ID: 63d4be79a70f
Revises: df53432df1b2
Create Date: 2026-08-03 16:28:34.887875

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '63d4be79a70f'
down_revision = 'df53432df1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'document_chunks', 'embedding',
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=Vector(384),
        existing_nullable=True,
        postgresql_using="(embedding::text)::vector(384)"
    )
    op.create_index(op.f('ix_document_chunks_organization_id'), 'document_chunks', ['organization_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_project_id'), 'document_chunks', ['project_id'], unique=False)
    op.drop_constraint(op.f('document_chunks_document_id_fkey'), 'document_chunks', type_='foreignkey')
    op.create_foreign_key(None, 'document_chunks', 'documents', ['document_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint(None, 'document_chunks', type_='foreignkey')
    op.create_foreign_key(op.f('document_chunks_document_id_fkey'), 'document_chunks', 'documents', ['document_id'], ['id'])
    op.drop_index(op.f('ix_document_chunks_project_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_organization_id'), table_name='document_chunks')
    op.alter_column(
        'document_chunks', 'embedding',
        existing_type=Vector(384),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="to_jsonb(embedding)"
    )