"""update logs schema

Revision ID: 44612a0d981d
Revises: 847599e9c240
Create Date: 2026-03-26 14:37:00.134735

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '44612a0d981d'
down_revision = '847599e9c240'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('method', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('path', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('headers', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('ip_address', sa.String(length=45), nullable=True))
        batch_op.add_column(sa.Column('response_status', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key('fk_logs_user_id_users', 'users', ['user_id'], ['id'])

    op.execute("UPDATE logs SET method = 'UNKNOWN' WHERE method IS NULL")
    op.execute("UPDATE logs SET path = '/' WHERE path IS NULL")
    op.execute("UPDATE logs SET ip_address = 'unknown' WHERE ip_address IS NULL")
    op.execute("UPDATE logs SET response_status = 0 WHERE response_status IS NULL")
    op.execute("UPDATE logs SET timestamp = created_at WHERE timestamp IS NULL")
    op.execute("UPDATE logs SET headers = '{}' WHERE headers IS NULL")

    with op.batch_alter_table('logs', schema=None) as batch_op:
        batch_op.alter_column('method', existing_type=sa.String(length=10), nullable=False)
        batch_op.alter_column('path', existing_type=sa.String(length=512), nullable=False)
        batch_op.alter_column('headers', existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column('ip_address', existing_type=sa.String(length=45), nullable=False)
        batch_op.alter_column('response_status', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('timestamp', existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.drop_column('message')
        batch_op.drop_column('created_at')
        batch_op.drop_column('level')
        batch_op.drop_column('metadata')


def downgrade():
    with op.batch_alter_table('logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('metadata', sqlite.JSON(), nullable=True))
        batch_op.add_column(sa.Column('level', sa.VARCHAR(length=20), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DATETIME(), nullable=True))
        batch_op.add_column(sa.Column('message', sa.TEXT(), nullable=True))
        batch_op.drop_constraint('fk_logs_user_id_users', type_='foreignkey')

    op.execute("UPDATE logs SET level = 'INFO' WHERE level IS NULL")
    op.execute("UPDATE logs SET message = path WHERE message IS NULL")
    op.execute("UPDATE logs SET created_at = timestamp WHERE created_at IS NULL")

    with op.batch_alter_table('logs', schema=None) as batch_op:
        batch_op.alter_column('level', existing_type=sa.VARCHAR(length=20), nullable=False)
        batch_op.alter_column('created_at', existing_type=sa.DATETIME(), nullable=False)
        batch_op.alter_column('message', existing_type=sa.TEXT(), nullable=False)
        batch_op.drop_column('timestamp')
        batch_op.drop_column('user_id')
        batch_op.drop_column('response_status')
        batch_op.drop_column('ip_address')
        batch_op.drop_column('headers')
        batch_op.drop_column('path')
        batch_op.drop_column('method')
