"""Durable application state, jobs, negotiation events, market cache and calls."""

from alembic import op
from maxx.schema import metadata

revision = "0001_application_state"
down_revision = None
branch_labels = None
depends_on = None


# Later migrations own the account tables, so 0001 stays the original six.
ORIGINAL = [
    "bloc_documents",
    "demand_signals",
    "negotiation_events",
    "negotiation_jobs",
    "price_cache",
    "model_calls",
]


def _tables():
    return [metadata.tables[name] for name in ORIGINAL]


def upgrade():
    metadata.create_all(op.get_bind(), tables=_tables(), checkfirst=True)


def downgrade():
    metadata.drop_all(op.get_bind(), tables=_tables())
