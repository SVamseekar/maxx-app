"""OpenID Connect nonce on pending OAuth sign-ins."""

import sqlalchemy as sa

from alembic import op

revision = "0003_oauth_nonce"
down_revision = "0002_accounts"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("oauth_states")}
    if "nonce" not in columns:  # fresh databases already got it from 0002's current metadata
        op.add_column("oauth_states", sa.Column("nonce", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("oauth_states", "nonce")
