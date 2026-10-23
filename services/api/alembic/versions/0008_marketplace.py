"""Marketplace: trader details, orders and fulfilment, cases, adjustments, audit log, flags."""

import sqlalchemy as sa

from alembic import op
from maxx import schema

revision = "0008_marketplace"
down_revision = "0007_sellers"
branch_labels = None
depends_on = None

NEW_TABLES = [
    schema.delivery_addresses,
    schema.orders,
    schema.cases,
    schema.case_events,
    schema.seller_adjustments,
    schema.audit_log,
    schema.system_flags,
]
SELLER_COLUMNS = [
    "legal_name",
    "business_type",
    "country",
    "address_line1",
    "address_city",
    "address_region",
    "address_postal",
    "phone",
    "support_email",
    "website",
    "trade_register_no",
    "ship_within_days",
    "ships_to",
    "return_days",
    "return_policy",
    "certified_at",
    "terms_version",
    "payout_verified_at",
    "review_note",
    "reviewed_at",
    "reviewed_by",
    "strikes",
]


def _add_missing(table, names):
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table.name)}
    for name in names:
        if name in existing:
            continue
        column = table.c[name]
        # Existing rows need a value for NOT NULL columns.
        default = column.default.arg if column.default is not None else None
        op.add_column(
            table.name,
            sa.Column(
                name,
                column.type,
                nullable=column.nullable,
                server_default=None if default is None else sa.text(repr(default)),
            ),
        )


def upgrade():
    # Fresh databases already created these columns from the current metadata in 0005/0007.
    _add_missing(schema.sellers, SELLER_COLUMNS)
    _add_missing(schema.payments, ["address_id"])
    _add_missing(schema.payouts, ["order_id"])
    schema.metadata.create_all(op.get_bind(), tables=NEW_TABLES, checkfirst=True)


def downgrade():
    schema.metadata.drop_all(op.get_bind(), tables=list(reversed(NEW_TABLES)))
