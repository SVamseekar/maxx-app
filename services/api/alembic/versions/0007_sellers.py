"""Seller onboarding: seller accounts and standing offers."""

from alembic import op
from maxx import schema

revision = "0007_sellers"
down_revision = "0006_used_transactions"
branch_labels = None
depends_on = None

TABLES = [schema.sellers, schema.seller_offers]


def upgrade():
    schema.metadata.create_all(op.get_bind(), tables=TABLES, checkfirst=True)


def downgrade():
    schema.metadata.drop_all(op.get_bind(), tables=list(reversed(TABLES)))
