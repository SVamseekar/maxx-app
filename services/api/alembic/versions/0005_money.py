"""Money layer: payments, PayPal events, payouts, settlements, subscriptions, simulator."""

from alembic import op
from maxx import schema

revision = "0005_money"
down_revision = "0004_security"
branch_labels = None
depends_on = None

TABLES = [
    schema.payments,
    schema.paypal_events,
    schema.payouts,
    schema.settlements,
    schema.subscriptions,
    schema.simulator_objects,
]


def upgrade():
    schema.metadata.create_all(op.get_bind(), tables=TABLES, checkfirst=True)


def downgrade():
    schema.metadata.drop_all(op.get_bind(), tables=list(reversed(TABLES)))
