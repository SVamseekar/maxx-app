"""Marketplace completion: notifications, carrier tracking, payout items, seller verification,
listings and AI seller agents."""

import sqlalchemy as sa

from alembic import op
from maxx import schema

revision = "0010_marketplace_completion"
down_revision = "0009_bloc_index"
branch_labels = None
depends_on = None

NEW_TABLES = [
    schema.tracking_events,
    schema.notifications,
    schema.notification_prefs,
    schema.sanctions_entries,
]
COLUMNS = {
    schema.payouts: [
        "payout_item_id",
        "item_status",
        "attempt",
        "failure_reason",
        "item_checked_at",
    ],
    schema.sellers: [
        "identity_status",
        "identity_session",
        "identity_name",
        "identity_country",
        "identity_checked_at",
        "screening_status",
        "screening_hits",
        "screened_at",
        "tax_id_enc",
        "tax_id_last4",
        "high_volume_since",
        "info_due_by",
        "recertify_by",
        "demo",
    ],
    schema.seller_offers: ["agent", "guidance", "listing", "gtin", "category", "typical_price"],
    schema.orders: [
        "simulated",
        "carrier_code",
        "tracker_id",
        "tracking_status",
        "tracking_detail",
        "tracking_checked_at",
        "first_scan_at",
        "estimated_delivery",
        "review_flag",
    ],
}


def _server_default(column):
    default = column.default.arg if column.default is not None else None
    if default is None:
        return None
    if isinstance(default, bool):
        return sa.false() if not default else sa.true()
    return sa.text(repr(default))


def upgrade():
    bind = op.get_bind()
    for table, names in COLUMNS.items():
        existing = {c["name"] for c in sa.inspect(bind).get_columns(table.name)}
        for name in names:
            if name in existing:
                continue
            column = table.c[name]
            op.add_column(
                table.name,
                sa.Column(
                    name,
                    column.type,
                    nullable=column.nullable,
                    server_default=_server_default(column),
                ),
            )
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("orders")}
    if "ix_orders_tracking" not in indexes:
        op.create_index("ix_orders_tracking", "orders", ["carrier_code", "tracking"])
    if "ix_orders_tracker_id" not in indexes:
        op.create_index("ix_orders_tracker_id", "orders", ["tracker_id"])
    schema.metadata.create_all(bind, tables=NEW_TABLES, checkfirst=True)
    # Existing sellers' first yearly re-certification falls one year after they joined.
    bind.execute(
        sa.text(
            "UPDATE sellers SET recertify_by = created_at + 31536000 WHERE recertify_by IS NULL"
        )
    )


def downgrade():
    schema.metadata.drop_all(op.get_bind(), tables=list(reversed(NEW_TABLES)))
    op.drop_index("ix_orders_tracker_id", "orders")
    op.drop_index("ix_orders_tracking", "orders")
    for table, names in COLUMNS.items():
        for name in names:
            op.drop_column(table.name, name)
