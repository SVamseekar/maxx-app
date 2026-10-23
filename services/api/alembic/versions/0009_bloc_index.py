"""Index columns on bloc_documents so lists, polling and workers do not parse documents."""

import json

import sqlalchemy as sa

from alembic import op
from maxx import schema

revision = "0009_bloc_index"
down_revision = "0008_marketplace"
branch_labels = None
depends_on = None

COLUMNS = [
    "generation",
    "status",
    "product_key",
    "closes_at",
    "owner_id",
    "title",
    "typical_price",
    "target_price",
    "mode",
    "scenario",
    "buyers",
    "committed",
    "participants",
    "seller_codes",
]


def upgrade():
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("bloc_documents")}
    for name in COLUMNS:
        if name in existing:
            continue
        column = schema.blocs.c[name]
        default = column.default.arg if column.default is not None else None
        op.add_column(
            "bloc_documents",
            sa.Column(
                name,
                column.type,
                nullable=column.nullable,
                server_default=None if default is None else sa.text(repr(default)),
            ),
        )
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("bloc_documents")}
    for name in ("status", "product_key", "owner_id"):
        index = f"ix_bloc_documents_{name}"
        if index not in indexes:
            op.create_index(index, "bloc_documents", [name])
    # Fill the new columns from each stored document.
    rows = bind.execute(sa.text("SELECT id, document FROM bloc_documents")).all()
    for row in rows:
        doc = json.loads(row.document)
        members = doc.get("members", [])
        users = sorted({m["user_id"] for m in members if not str(m["user_id"]).startswith("seed-")})
        bind.execute(
            sa.text(
                "UPDATE bloc_documents SET generation=:g, status=:s, product_key=:k, "
                "closes_at=:c, owner_id=:o, title=:t, typical_price=:tp, target_price=:gp, "
                "mode=:m, scenario=:sc, buyers=:b, committed=:cm, participants=:p, "
                "seller_codes=:sl WHERE id=:id"
            ),
            {
                "g": doc.get("generation", 0),
                "s": doc.get("status", "OPEN"),
                "k": doc.get("product_key", ""),
                "c": doc.get("closes_at", 0),
                "o": doc.get("owner_id"),
                "t": doc.get("title", "")[:300],
                "tp": doc.get("typical_price", 0),
                "gp": doc.get("target_price"),
                "m": doc.get("mode", "fixture"),
                "sc": doc.get("scenario", "success"),
                "b": sum(m["status"] != "LEFT" for m in members),
                "cm": sum(float(m["max_price"]) for m in members if m["status"] == "HELD"),
                "p": "|" + "|".join(users) + "|" if users else "",
                "sl": "|" + "|".join(s["id"] for s in doc.get("sellers", [])) + "|"
                if doc.get("sellers")
                else "",
                "id": row.id,
            },
        )


def downgrade():
    for name in COLUMNS:
        op.drop_column("bloc_documents", name)
