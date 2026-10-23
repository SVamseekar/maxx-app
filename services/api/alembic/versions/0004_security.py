"""Security hardening: two-step verification, passkeys, trusted devices, events, freshness."""

import sqlalchemy as sa

from alembic import op
from maxx import schema

revision = "0004_security"
down_revision = "0003_oauth_nonce"
branch_labels = None
depends_on = None

NEW_TABLES = [
    schema.recovery_codes,
    schema.passkeys,
    schema.webauthn_challenges,
    schema.trusted_devices,
    schema.security_events,
]
USER_COLUMNS = {
    "totp_secret_enc": sa.Column("totp_secret_enc", sa.Text, nullable=True),
    "totp_pending_enc": sa.Column("totp_pending_enc", sa.Text, nullable=True),
    "totp_enabled": sa.Column(
        "totp_enabled", sa.Boolean, nullable=False, server_default=sa.false()
    ),
    "totp_last_step": sa.Column("totp_last_step", sa.BigInteger, nullable=True),
}
SESSION_COLUMNS = {
    "recent_auth_at": sa.Column(
        "recent_auth_at", sa.BigInteger, nullable=False, server_default="0"
    ),
    "auth_method": sa.Column("auth_method", sa.String(30), nullable=False, server_default=""),
}


def _add_missing(table: str, wanted: dict):
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    for name, column in wanted.items():
        if name not in existing:  # fresh databases already got them from 0002's current metadata
            op.add_column(table, column)


def upgrade():
    _add_missing("users", USER_COLUMNS)
    _add_missing("auth_sessions", SESSION_COLUMNS)
    schema.metadata.create_all(op.get_bind(), tables=NEW_TABLES, checkfirst=True)


def downgrade():
    schema.metadata.drop_all(op.get_bind(), tables=list(reversed(NEW_TABLES)))
    for name in SESSION_COLUMNS:
        op.drop_column("auth_sessions", name)
    for name in USER_COLUMNS:
        op.drop_column("users", name)
