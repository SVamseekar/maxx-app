"""Application tables shared by Alembic and storage; Postgres is the runtime store."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
)

metadata = MetaData()
blocs = Table(
    "bloc_documents",
    metadata,
    Column("id", String(100), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("document", Text, nullable=False),
    # Denormalised from the document so lists, polling and workers never parse it. Kept in step
    # by BlocStore on every write.
    Column("generation", BigInteger, nullable=False, default=0),
    Column("status", String(12), nullable=False, default="OPEN", index=True),
    Column("product_key", String(300), nullable=False, default="", index=True),
    Column("closes_at", BigInteger, nullable=False, default=0),
    Column("owner_id", String(36), nullable=True, index=True),
    Column("title", String(300), nullable=False, default=""),
    Column("typical_price", Numeric(12, 2), nullable=False, default=0),
    Column("target_price", Numeric(12, 2), nullable=True),
    Column("mode", String(10), nullable=False, default="fixture"),
    Column("scenario", String(10), nullable=False, default="success"),
    Column("buyers", Integer, nullable=False, default=0),
    Column("committed", Numeric(14, 2), nullable=False, default=0),
    Column("participants", Text, nullable=False, default=""),
    Column("seller_codes", Text, nullable=False, default=""),
)
demands = Table(
    "demand_signals",
    metadata,
    Column("id", String(100), primary_key=True),
    Column("document", Text, nullable=False),
)
events = Table(
    "negotiation_events",
    metadata,
    Column("bloc_id", String(100), primary_key=True),
    Column("generation", BigInteger, primary_key=True),
    Column("event_id", Integer, primary_key=True),
    Column("document", Text, nullable=False),
)
jobs = Table(
    "negotiation_jobs",
    metadata,
    Column("bloc_id", String(100), primary_key=True),
    Column("status", String(20), nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)
cache = Table(
    "price_cache",
    metadata,
    Column("product_key", String(64), primary_key=True),
    Column("expires_at", BigInteger, nullable=False),
    Column("document", Text, nullable=False),
)
calls = Table(
    "model_calls",
    metadata,
    Column("id", String(100), primary_key=True),
    Column("created_at", BigInteger, nullable=False),
    Column("metadata", Text, nullable=False),
)

# Accounts. Passwords are salted scrypt hashes; session and one-time tokens are stored only as
# SHA-256 digests, so a database read cannot be replayed as a login.
users = Table(
    "users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("email_verified", Boolean, nullable=False, default=False),
    Column("password_hash", Text, nullable=True),
    Column("display_name", String(80), nullable=False),
    Column("avatar_url", Text, nullable=True),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    Column("last_login_at", BigInteger, nullable=True),
    # Two-step verification. Seeds are AES-GCM encrypted (maxx.secrets); last_step blocks replays.
    Column("totp_secret_enc", Text, nullable=True),
    Column("totp_pending_enc", Text, nullable=True),
    Column("totp_enabled", Boolean, nullable=False, default=False),
    Column("totp_last_step", BigInteger, nullable=True),
)
identities = Table(
    "oauth_identities",
    metadata,
    Column("provider", String(20), primary_key=True),
    Column("subject", String(255), primary_key=True),
    Column("user_id", String(36), nullable=False, index=True),
    Column("email", String(320), nullable=True),
    Column("created_at", BigInteger, nullable=False),
)
sessions = Table(
    "auth_sessions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("user_id", String(36), nullable=False, index=True),
    Column("created_at", BigInteger, nullable=False),
    Column("last_seen_at", BigInteger, nullable=False),
    Column("expires_at", BigInteger, nullable=False),
    Column("user_agent", String(200), nullable=False, default=""),
    Column("recent_auth_at", BigInteger, nullable=False, default=0),
    Column("auth_method", String(30), nullable=False, default=""),
)
auth_tokens = Table(
    "auth_tokens",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("user_id", String(36), nullable=False, index=True),
    Column("purpose", String(30), nullable=False),
    Column("email", String(320), nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("expires_at", BigInteger, nullable=False),
    Column("used_at", BigInteger, nullable=True),
)
oauth_states = Table(
    "oauth_states",
    metadata,
    Column("state", String(64), primary_key=True),
    Column("provider", String(20), nullable=False),
    Column("verifier", String(128), nullable=False),
    Column("next_path", String(300), nullable=False),
    Column("link_user_id", String(36), nullable=True),
    Column("expires_at", BigInteger, nullable=False),
    Column("nonce", String(64), nullable=True),
)
Index("ix_auth_sessions_expires", sessions.c.expires_at)

recovery_codes = Table(
    "recovery_codes",
    metadata,
    Column("user_id", String(36), primary_key=True),
    Column("code_hash", String(64), primary_key=True),
    Column("used_at", BigInteger, nullable=True),
)
passkeys = Table(
    "passkeys",
    metadata,
    Column("id", String(512), primary_key=True),  # credential id, base64url
    Column("user_id", String(36), nullable=False, index=True),
    Column("public_key", Text, nullable=False),  # base64url COSE key
    Column("sign_count", BigInteger, nullable=False, default=0),
    Column("name", String(80), nullable=False),
    Column("transports", String(120), nullable=False, default=""),
    Column("aaguid", String(40), nullable=False, default=""),
    Column("backup_eligible", Boolean, nullable=False, default=False),
    Column("backup_state", Boolean, nullable=False, default=False),
    Column("created_at", BigInteger, nullable=False),
    Column("last_used_at", BigInteger, nullable=True),
)
webauthn_challenges = Table(
    "webauthn_challenges",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("purpose", String(20), nullable=False),
    Column("user_id", String(36), nullable=True),
    Column("challenge", String(128), nullable=False),
    Column("expires_at", BigInteger, nullable=False),
)
trusted_devices = Table(
    "trusted_devices",
    metadata,
    Column("id", String(64), primary_key=True),  # SHA-256 of the cookie value
    Column("user_id", String(36), nullable=False, index=True),
    Column("user_agent", String(200), nullable=False, default=""),
    Column("created_at", BigInteger, nullable=False),
    Column("last_used_at", BigInteger, nullable=False),
    Column("expires_at", BigInteger, nullable=False),
)
security_events = Table(
    "security_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("created_at", BigInteger, nullable=False, index=True),
    Column("ip_prefix", String(64), nullable=False, default=""),
    Column("user_agent", String(200), nullable=False, default=""),
    Column("detail", String(300), nullable=False, default=""),
)

# Money layer. Amounts are Numeric(12, 2); every PayPal id is kept so receipts and
# reconciliation can be checked against PayPal itself.
payments = Table(
    "payments",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("kind", String(12), nullable=False),  # hold | checkout
    Column("bloc_id", String(100), nullable=True, index=True),
    Column("generation", BigInteger, nullable=False, default=0),
    Column("member_id", String(36), nullable=True, index=True),
    Column("user_id", String(36), nullable=True, index=True),
    Column("order_id", String(64), nullable=False, index=True),
    Column("authorization_id", String(64), nullable=True, index=True),
    Column("capture_id", String(64), nullable=True),
    Column("max_amount", Numeric(12, 2), nullable=False),
    Column("captured_amount", Numeric(12, 2), nullable=True),
    Column("currency", String(3), nullable=False, default="USD"),
    Column("status", String(20), nullable=False),
    Column("simulated", Boolean, nullable=False, default=False),
    Column("error", String(200), nullable=False, default=""),
    Column("meta", Text, nullable=False, default=""),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    Column("address_id", String(36), nullable=True),
)
paypal_events = Table(
    "paypal_events",
    metadata,
    Column("event_id", String(80), primary_key=True),
    Column("event_type", String(80), nullable=False),
    Column("resource_id", String(80), nullable=False, default=""),
    Column("received_at", BigInteger, nullable=False),
    Column("verified", Boolean, nullable=False, default=False),
    Column("processed", Boolean, nullable=False, default=False),
    Column("summary", String(300), nullable=False, default=""),
)
payouts = Table(
    "payouts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("bloc_id", String(100), nullable=False, index=True),
    Column("generation", BigInteger, nullable=False, default=0),
    Column("seller_id", String(10), nullable=False),
    Column("method", String(10), nullable=False, default="paypal"),  # paypal | pyusd
    Column("gross_amount", Numeric(12, 2), nullable=False),
    Column("fee_amount", Numeric(12, 2), nullable=False),
    Column("net_amount", Numeric(12, 2), nullable=False),
    Column("units", Integer, nullable=False, default=0),
    Column("sender_batch_id", String(80), nullable=False, unique=True),
    Column("paypal_batch_id", String(64), nullable=True),
    Column("receiver", String(320), nullable=False, default=""),
    Column("status", String(20), nullable=False),
    Column("tx_hash", String(100), nullable=True),
    Column("simulated", Boolean, nullable=False, default=False),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    Column("order_id", String(36), nullable=True, index=True),
    # A batch being accepted is not the money arriving: PayPal settles each item separately, and an
    # item can still be unclaimed, returned or blocked. These follow the item to its end.
    Column("payout_item_id", String(64), nullable=True),
    Column("item_status", String(20), nullable=False, default=""),
    Column("attempt", Integer, nullable=False, default=1),
    Column("failure_reason", String(120), nullable=False, default=""),
    Column("item_checked_at", BigInteger, nullable=True),
)
settlements = Table(
    "settlements",
    metadata,
    Column("bloc_id", String(100), primary_key=True),
    Column("generation", BigInteger, primary_key=True),
    Column("status", String(12), nullable=False),
    Column("started_at", BigInteger, nullable=False),
    Column("finished_at", BigInteger, nullable=True),
    Column("summary", Text, nullable=False, default="{}"),
)
subscriptions = Table(
    "subscriptions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("user_id", String(36), nullable=False, index=True),
    Column("plan", String(10), nullable=False),
    Column("status", String(20), nullable=False),
    Column("simulated", Boolean, nullable=False, default=False),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)
simulator_objects = Table(
    "simulator_objects",
    metadata,
    Column("key", String(120), primary_key=True),
    Column("document", Text, nullable=False),
)

# One row per accepted on-chain payment. The primary key makes "this transaction already paid an
# order" an atomic fact instead of a check-then-write.
used_transactions = Table(
    "used_transactions",
    metadata,
    Column("tx_hash", String(66), primary_key=True),
    Column("payment_id", String(36), nullable=False),
    Column("used_at", BigInteger, nullable=False),
)

# Sellers. A seller is an account that has applied, accepted the terms and proved control of the
# email address its payouts go to. Offers are standing: they join any later Bloc for the product.
sellers = Table(
    "sellers",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), nullable=False, unique=True),
    Column("code", String(10), nullable=False, unique=True),
    Column("business_name", String(120), nullable=False),
    Column("payout_email", String(320), nullable=False),
    Column("payout_verified", Boolean, nullable=False, default=False),
    Column("status", String(12), nullable=False),  # PENDING | ACTIVE | SUSPENDED
    Column("terms_accepted_at", BigInteger, nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    # Trader details (EU Digital Services Act art. 30 and the US INFORM Act ask for these).
    Column("legal_name", String(160), nullable=False, default=""),
    Column("business_type", String(12), nullable=False, default="company"),
    Column("country", String(2), nullable=False, default=""),
    Column("address_line1", String(200), nullable=False, default=""),
    Column("address_city", String(100), nullable=False, default=""),
    Column("address_region", String(100), nullable=False, default=""),
    Column("address_postal", String(20), nullable=False, default=""),
    Column("phone", String(40), nullable=False, default=""),
    Column("support_email", String(320), nullable=False, default=""),
    Column("website", String(300), nullable=False, default=""),
    Column("trade_register_no", String(60), nullable=False, default=""),
    # Commitments buyers can rely on.
    Column("ship_within_days", Integer, nullable=False, default=3),
    Column("ships_to", String(200), nullable=False, default=""),
    Column("return_days", Integer, nullable=False, default=14),
    Column("return_policy", String(1000), nullable=False, default=""),
    Column("certified_at", BigInteger, nullable=True),
    Column("terms_version", String(20), nullable=False, default=""),
    Column("payout_verified_at", BigInteger, nullable=True),
    Column("review_note", String(500), nullable=False, default=""),
    Column("reviewed_at", BigInteger, nullable=True),
    Column("reviewed_by", String(36), nullable=True),
    Column("strikes", Integer, nullable=False, default=0),
    # Identity check by a verification provider. Only the outcome, the verified name and the
    # document country are kept; documents and selfies stay with the provider.
    Column("identity_status", String(20), nullable=False, default="none"),
    Column("identity_session", String(80), nullable=True),
    Column("identity_name", String(160), nullable=False, default=""),
    Column("identity_country", String(2), nullable=False, default=""),
    Column("identity_checked_at", BigInteger, nullable=True),
    # Sanctions screening against the OFAC lists: clear | review | blocked.
    Column("screening_status", String(10), nullable=False, default="clear"),
    Column("screening_hits", Text, nullable=False, default="[]"),
    Column("screened_at", BigInteger, nullable=True),
    # US INFORM Consumers Act: high-volume sellers give a tax id and re-certify every year.
    Column("tax_id_enc", Text, nullable=True),
    Column("tax_id_last4", String(4), nullable=False, default=""),
    Column("high_volume_since", BigInteger, nullable=True),
    Column("info_due_by", BigInteger, nullable=True),
    Column("recertify_by", BigInteger, nullable=True),
    # A judge's demo seller: simulator money only, never paid for real.
    Column("demo", Boolean, nullable=False, default=False),
)
seller_offers = Table(
    "seller_offers",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("seller_id", String(36), nullable=False, index=True),
    Column("product_key", String(300), nullable=False),
    Column("title", String(300), nullable=False),
    Column("stock", Integer, nullable=False),
    Column("floor", Numeric(12, 2), nullable=False),
    Column("opening_price", Numeric(12, 2), nullable=False),
    Column("strategy", String(10), nullable=False),  # firm | balanced | eager
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    # rules: a fixed concession per round. ai: a language-model agent inside the same hard limits.
    Column("agent", String(10), nullable=False, default="rules"),
    Column("guidance", String(280), nullable=False, default=""),
    # A listing is an offer the seller published before any buyer asked: it opens its own Bloc.
    Column("listing", Boolean, nullable=False, default=False),
    Column("gtin", String(14), nullable=False, default=""),
    Column("category", String(40), nullable=False, default=""),
    Column("typical_price", Numeric(12, 2), nullable=True),
)
Index(
    "ux_seller_offer_product", seller_offers.c.seller_id, seller_offers.c.product_key, unique=True
)

# Fulfilment. Maxx does not ship anything: the seller does. These tables only coordinate it.
delivery_addresses = Table(
    "delivery_addresses",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), nullable=False, index=True),
    Column("label", String(60), nullable=False, default=""),
    Column("country", String(2), nullable=False),
    Column("ciphertext", Text, nullable=False),  # name, lines, city, postal, phone: encrypted
    Column("created_at", BigInteger, nullable=False),
    Column("deleted_at", BigInteger, nullable=True),
)
orders = Table(
    "orders",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("payment_id", String(36), nullable=False, unique=True),
    Column("bloc_id", String(100), nullable=False, index=True),
    Column("generation", BigInteger, nullable=False),
    Column("buyer_id", String(36), nullable=False, index=True),
    Column("seller_code", String(10), nullable=False, index=True),
    Column("seller_user_id", String(36), nullable=False, index=True),
    Column("title", String(300), nullable=False),
    Column("amount", Numeric(12, 2), nullable=False),
    Column("currency", String(3), nullable=False, default="USD"),
    Column("status", String(20), nullable=False),
    Column("ship_by", BigInteger, nullable=False),
    Column("carrier", String(40), nullable=False, default=""),
    Column("tracking", String(80), nullable=False, default=""),
    Column("shipped_at", BigInteger, nullable=True),
    Column("delivered_at", BigInteger, nullable=True),
    Column("closed_at", BigInteger, nullable=True),
    Column("address_blob", Text, nullable=True),
    Column("address_country", String(2), nullable=False, default=""),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    # Won from one of the clearly labelled simulated sellers: an automatic stand-in ships it.
    Column("simulated", Boolean, nullable=False, default=False),
    # Carrier tracking, as the carrier (through the tracking provider) reports it.
    Column("carrier_code", String(30), nullable=False, default=""),
    Column("tracker_id", String(80), nullable=True, index=True),
    Column("tracking_status", String(30), nullable=False, default=""),
    Column("tracking_detail", String(60), nullable=False, default=""),
    Column("tracking_checked_at", BigInteger, nullable=True),
    Column("first_scan_at", BigInteger, nullable=True),
    Column("estimated_delivery", BigInteger, nullable=True),
    # Why a payout is on hold for a person to look at (for example a reused tracking number).
    Column("review_flag", String(120), nullable=False, default=""),
)
Index("ix_orders_tracking", orders.c.carrier_code, orders.c.tracking)
tracking_events = Table(
    "tracking_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("order_id", String(36), nullable=False, index=True),
    Column("status", String(30), nullable=False),
    Column("message", String(200), nullable=False, default=""),
    Column("location", String(120), nullable=False, default=""),
    Column("at", BigInteger, nullable=False),
)
cases = Table(
    "cases",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("order_id", String(36), nullable=False, index=True),
    Column("opened_by", String(36), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("opened_at", BigInteger, nullable=False),
    Column("respond_by", BigInteger, nullable=False),
    Column("resolved_at", BigInteger, nullable=True),
    Column("resolution", String(500), nullable=False, default=""),
)
case_events = Table(
    "case_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("case_id", String(36), nullable=False, index=True),
    Column("actor", String(10), nullable=False),  # buyer | seller | maxx
    Column("body", String(2000), nullable=False),
    Column("created_at", BigInteger, nullable=False),
)
seller_adjustments = Table(
    "seller_adjustments",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("seller_code", String(10), nullable=False, index=True),
    Column("order_id", String(36), nullable=False),
    Column("amount", Numeric(12, 2), nullable=False),  # money the seller owes Maxx
    Column("reason", String(200), nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("settled_at", BigInteger, nullable=True),
)
# An append-only record of money and trust decisions, for investigations.
audit_log = Table(
    "audit_log",
    metadata,
    Column(
        "id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    ),
    Column("at", BigInteger, nullable=False, index=True),
    Column("actor", String(40), nullable=False),
    Column("action", String(40), nullable=False, index=True),
    Column("subject", String(80), nullable=False, default=""),
    Column("detail", String(300), nullable=False, default=""),
)
system_flags = Table(
    "system_flags",
    metadata,
    Column("key", String(40), primary_key=True),
    Column("value", String(200), nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)

# Notifications. Every row is an in-app message; its email is delivered from here by the worker
# (a transactional outbox), so a mail outage delays a message instead of losing it.
notifications = Table(
    "notifications",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("title", String(160), nullable=False),
    Column("body", String(600), nullable=False, default=""),
    Column("link", String(300), nullable=False, default=""),
    Column("created_at", BigInteger, nullable=False),
    Column("read_at", BigInteger, nullable=True),
    Column("email_status", String(10), nullable=False, default="QUEUED"),
    Column("email_attempts", Integer, nullable=False, default=0),
    Column("email_next_at", BigInteger, nullable=False, default=0),
    Column("email_error", String(120), nullable=False, default=""),
    # Makes "send this once" (for example one reminder per deadline) an atomic fact.
    Column("dedupe_key", String(160), nullable=True, unique=True),
)
Index("ix_notifications_email", notifications.c.email_status, notifications.c.email_next_at)
notification_prefs = Table(
    "notification_prefs",
    metadata,
    Column("user_id", String(36), primary_key=True),
    Column("kind", String(40), primary_key=True),
    Column("email", Boolean, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)

# OFAC sanctions list entries (primary names and aliases), refreshed from the public files.
sanctions_entries = Table(
    "sanctions_entries",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("entry_id", String(20), nullable=False, index=True),
    Column("name", String(400), nullable=False),
    Column("normalized", String(400), nullable=False),
    Column("kind", String(20), nullable=False, default=""),
    Column("program", String(200), nullable=False, default=""),
)
