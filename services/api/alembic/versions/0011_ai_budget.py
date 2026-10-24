"""The AI spending cap: budget limits and per-call holds."""

from alembic import op
from maxx import schema

revision = "0011_ai_budget"
down_revision = "0010_marketplace_completion"
branch_labels = None
depends_on = None

NEW_TABLES = [schema.ai_budget, schema.ai_reservations]


def upgrade():
    schema.metadata.create_all(op.get_bind(), tables=NEW_TABLES, checkfirst=True)


def downgrade():
    schema.metadata.drop_all(op.get_bind(), tables=list(reversed(NEW_TABLES)))
