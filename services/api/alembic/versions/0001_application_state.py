"""Durable application state, jobs, negotiation events, market cache and calls."""

from alembic import op
from maxx.schema import metadata

revision = "0001_application_state"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    metadata.drop_all(op.get_bind())
