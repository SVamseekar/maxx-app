"""Atomic replay protection for on-chain payments."""

from alembic import op
from maxx import schema

revision = "0006_used_transactions"
down_revision = "0005_money"
branch_labels = None
depends_on = None


def upgrade():
    schema.metadata.create_all(op.get_bind(), tables=[schema.used_transactions], checkfirst=True)


def downgrade():
    schema.metadata.drop_all(op.get_bind(), tables=[schema.used_transactions])
