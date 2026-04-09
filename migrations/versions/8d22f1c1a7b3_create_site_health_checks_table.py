"""create site health checks table

Revision ID: 8d22f1c1a7b3
Revises: 44612a0d981d
Create Date: 2026-04-09 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8d22f1c1a7b3'
down_revision = '44612a0d981d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'site_health_checks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_up', sa.Boolean(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_site_health_checks_site_id', 'site_health_checks', ['site_id'], unique=False)
    op.create_index('ix_site_health_checks_checked_at', 'site_health_checks', ['checked_at'], unique=False)


def downgrade():
    op.drop_index('ix_site_health_checks_checked_at', table_name='site_health_checks')
    op.drop_index('ix_site_health_checks_site_id', table_name='site_health_checks')
    op.drop_table('site_health_checks')