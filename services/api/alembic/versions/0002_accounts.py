"""Accounts: users, linked OAuth identities, sessions, one-time tokens and OAuth state."""

from alembic import op
from maxx import schema

revision = "0002_accounts"
down_revision = "0001_application_state"
branch_labels = None
depends_on = None

TABLES = [
    schema.users,
    schema.identities,
    schema.sessions,
    schema.auth_tokens,
    schema.oauth_states,
]


def upgrade():
    # checkfirst keeps this safe on databases where create_all already ran.
    schema.metadata.create_all(op.get_bind(), tables=TABLES, checkfirst=True)


def downgrade():
    schema.metadata.drop_all(op.get_bind(), tables=list(reversed(TABLES)))
