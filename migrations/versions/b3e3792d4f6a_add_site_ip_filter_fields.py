"""add site ip filter fields

Revision ID: b3e3792d4f6a
Revises: 8d22f1c1a7b3
Create Date: 2026-04-09 17:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3e3792d4f6a'
down_revision = '8d22f1c1a7b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('enable_ip_filter', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column('ip_filter_mode', sa.String(length=10), nullable=False, server_default='whitelist')
        )

    op.create_table(
        'ip_filters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.alter_column('enable_ip_filter', server_default=None)
        batch_op.alter_column('ip_filter_mode', server_default=None)


def downgrade():
    op.drop_table('ip_filters')

    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.drop_column('ip_filter_mode')
        batch_op.drop_column('enable_ip_filter')