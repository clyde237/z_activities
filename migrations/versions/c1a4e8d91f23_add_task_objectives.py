"""add optional objectives to tasks

Revision ID: c1a4e8d91f23
Revises: a2078873f19e
Create Date: 2026-09-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1a4e8d91f23"
down_revision = "a2078873f19e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("objectives", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_column("objectives")
