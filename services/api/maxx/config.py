from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://maxx:maxx_local@127.0.0.1:55432/maxx"
    # Token Factory prices per million tokens, as its own /v1/models?verbose=true listed them on
    # 24 Oct 2026 (images are billed as input tokens). A model missing here is never called.
    model_rates_json: str = (
        '{"nvidia/Nemotron-3_5-Lightning": {"input_usd_per_million": "0.06", '
        '"output_usd_per_million": "0.24", "effective_date": "2026-10-24"}, '
        '"nvidia/nemotron-3-super-120b-a12b": {"input_usd_per_million": "0.30", '
        '"output_usd_per_million": "0.90", "effective_date": "2026-10-24"}, '
        '"nvidia/Nemotron-3-Ultra-550b-a55b": {"input_usd_per_million": "1.00", '
        '"output_usd_per_million": "3.00", "effective_date": "2026-10-24"}, '
        '"nvidia/Nemotron-3.5-Super-VL": {"input_usd_per_million": "0.30", '
        '"output_usd_per_million": "0.90", "effective_date": "2026-10-24", "image_tokens": 1800}, '
        '"google/gemma-3-27b-it": {"input_usd_per_million": "0.10", '
        '"output_usd_per_million": "0.30", "effective_date": "2026-10-24", "image_tokens": 256}, '
        '"Qwen/Qwen3-Embedding-8B": {"input_usd_per_million": "0.01", '
        '"output_usd_per_million": "0", "effective_date": "2026-10-24"}}'
    )
    # The AI spending cap. Every paid call reserves its worst-case cost against all of these first;
    # see docs/ai-guardrails.md. Amounts are US dollars as strings; days are UTC.
    ai_budget_usd: str = "20"
    ai_daily_budget_usd: str = "0.40"
    ai_anonymous_daily_budget_usd: str = "0.08"
    ai_address_daily_budget_usd: str = "0.02"
    ai_user_daily_budget_usd: str = "0.05"
    ai_premium_user_daily_budget_usd: str = "0.25"
    ai_paused: bool = False  # the operator's kill switch; the admin console has one too
    ai_anonymous_live: bool = True  # false: visitors must sign in before any live AI call
    ai_max_calls_per_scan: int = Field(default=10, ge=1, le=50)
    ai_max_calls_per_negotiation: int = Field(default=120, ge=1, le=500)
    ai_negotiation_worst_usd: str = "0.10"
    # Part of each day kept for negotiations; people's scans and matches share the rest.
    ai_negotiation_daily_budget_usd: str = "0.20"
    ai_owner_negotiation_daily_budget_usd: str = "0.10"  # per Bloc creator, within that share
    ai_verify_budget_usd: str = "1"  # the most one `make verify-guardrails` run may spend
    tavily_monthly_credits: int = Field(default=900, ge=0)
    tavily_daily_credits: int = Field(default=40, ge=0)
    bloc_open_seconds: int = Field(default=3600, ge=5, le=604800)
    worker_enabled: bool = True
    match_mode: str = "fixture"
    model_embed: str = "Qwen/Qwen3-Embedding-8B"
    scan_mode: str = "live"
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    tavily_api_key: str = ""
    model_vision: str = "google/gemma-3-27b-it"
    model_fast: str = "nvidia/Nemotron-3_5-Lightning"
    model_reason: str = "nvidia/nemotron-3-super-120b-a12b"
    provider_timeout: float = 20
    negotiation_mode: str = "fixture"
    model_seller: str = "nvidia/nemotron-3-super-120b-a12b"
    model_negotiator: str = "nvidia/Nemotron-3-Ultra-550b-a55b"
    negotiation_timeout: float = 90
    fixture_round_delay: float = 0.4
    # Deployment posture. `production` turns on startup checks that refuse insecure settings.
    environment: str = "development"
    # Master key for encrypting secrets stored in the database (TOTP seeds). 32+ random characters.
    # In development it is generated once into .local/secret_key; production must set it.
    secret_key: str = ""
    allowed_hosts: str = "*"
    docs_enabled: bool | None = None  # default: on in development, off in production
    # Database connections. The default pool (5) starves under a crowd; size it to the workers.
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    db_pool_recycle: int = Field(default=1800, ge=60)
    list_cache_seconds: float = Field(default=1.0, ge=0, le=30)
    max_body_bytes: int = Field(default=65536, ge=1024)
    api_rate_per_minute: int = Field(default=600, ge=10)
    stream_connections_per_ip: int = Field(default=6, ge=1)
    stream_connections_per_bloc: int = Field(default=200, ge=1)
    # Money layer. `off` keeps the original no-payment demo; `simulator` runs an in-process PayPal
    # stand-in (clearly labelled) so everything works without keys; `sandbox` talks to PayPal's
    # sandbox with real credentials. Live production money is intentionally not supported.
    paypal_mode: str = "off"
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_currency: str = "USD"
    paypal_sdk_url: str = "https://www.sandbox.paypal.com/web-sdk/v6/core"
    platform_fee_percent: str = "5"
    settlement_concurrency: int = Field(default=10, ge=1, le=50)
    paypal_negative_testing: bool = False
    checkout_max_amount: str = "500"
    checkout_premium_max_amount: str = "2000"
    paypal_plan_weekly: str = ""
    paypal_plan_yearly: str = ""
    checkout_proposal_minutes: int = Field(default=10, ge=1, le=60)
    paypal_seller_receiver: str = "sb-seller@maxx.example"
    # Sellers: `auto` activates a seller once their payout email is confirmed; `manual` also
    # needs an administrator's approval (required in production).
    seller_review: str = "auto"
    # Marketplace rules. Sellers are paid when they ship; unshipped orders are refunded.
    ship_grace_days: int = Field(default=2, ge=0, le=14)
    address_wait_days: int = Field(default=7, ge=1, le=30)
    delivery_auto_confirm_days: int = Field(default=14, ge=1, le=60)
    address_retention_days: int = Field(default=90, ge=1, le=730)
    payout_cooldown_hours: int = Field(default=0, ge=0, le=720)
    case_response_hours: int = Field(default=24, ge=1, le=240)
    # Carrier tracking: off | simulator | easypost. With tracking on, a seller is paid once the
    # carrier has the parcel (established sellers) or once it is delivered (new sellers).
    tracking_mode: str = "simulator"
    easypost_api_key: str = ""
    easypost_webhook_secret: str = ""
    easypost_base_url: str = "https://api.easypost.com"
    tracking_sim_step_seconds: int = Field(default=60, ge=1, le=86400)
    tracking_poll_minutes: int = Field(default=30, ge=1, le=1440)
    tracking_no_scan_days: int = Field(default=4, ge=1, le=30)
    payout_trusted_after_deliveries: int = Field(default=5, ge=0, le=1000)
    # Identity checks for sellers: off | simulator | stripe (Stripe Identity).
    verify_mode: str = "simulator"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_base_url: str = "https://api.stripe.com"
    seller_identity_required: bool = True
    # Sanctions screening: names at or above this similarity to an OFAC entry go to a person.
    sanctions_threshold: float = Field(default=0.9, ge=0.5, le=1.0)
    sanctions_sdn_url: str = (
        "https://sanctionslistservice.ofac.treas.gov/api/publicationpreview/exports/sdn.csv"
    )
    sanctions_alt_url: str = (
        "https://sanctionslistservice.ofac.treas.gov/api/publicationpreview/exports/alt.csv"
    )
    # US INFORM Consumers Act thresholds (200 sales and $5,000 in a 12-month period).
    high_volume_sales: int = Field(default=200, ge=1)
    high_volume_revenue: str = "5000"
    seller_info_days: int = Field(default=10, ge=1, le=60)
    # Listings sellers publish before any buyer asks.
    listing_max_per_seller: int = Field(default=20, ge=1, le=500)
    # A language-model seller agent may never cut more than this share of its opening price in
    # one round, whatever it proposes.
    seller_ai_max_round_drop_percent: str = "15"
    # The eight personas in every buyer-started Bloc. They are labelled everywhere, and an
    # automatic stand-in ships what they sell, so a buyer's journey always completes.
    simulated_sellers: bool = True
    simulated_seller_ship_seconds: int = Field(default=30, ge=0, le=86400)
    # The judge's seller tour (/judge): creates a demo seller and demo buyers. Simulator only.
    demo_tools: bool | None = None  # default: on in development, off in production
    email_max_attempts: int = Field(default=6, ge=1, le=20)
    # Spending limits and the emergency brake.
    hold_max_amount: str = "1000"
    # Above these amounts the person must have confirmed their identity recently.
    hold_reauth_over: str = "300"
    checkout_reauth_over: str = "200"
    hold_open_max_per_user: int = Field(default=10, ge=1, le=100)
    hold_outstanding_max_per_user: str = "3000"
    payments_frozen: bool = False
    simulator_webhook_secret: str = "maxx-simulator-signing-secret"
    # PYUSD (PayPal's stablecoin) settlement proof. Read-only: Maxx never holds a wallet key.
    pyusd_rpc_url: str = ""
    pyusd_chain: str = "ethereum-sepolia"
    pyusd_contract: str = ""
    pyusd_deposit_address: str = ""
    pyusd_min_confirmations: int = Field(default=3, ge=1, le=64)
    # Accounts and sessions. The public base URL is the browser-facing web origin.
    public_base_url: str = "http://localhost:3001"
    extra_allowed_origins: str = "http://127.0.0.1:3001"
    session_days: int = Field(default=30, ge=1, le=365)  # absolute lifetime of a sign-in
    session_idle_days: int = Field(
        default=14, ge=1, le=365
    )  # signed out after this much inactivity
    reauth_minutes: int = Field(
        default=10, ge=1, le=120
    )  # how long a password/passkey check stays fresh
    trusted_device_days: int = Field(default=30, ge=1, le=90)
    hibp_enabled: bool = True
    hibp_url: str = "https://api.pwnedpasswords.com/range/"
    turnstile_site_key: str = ""
    turnstile_secret: str = ""
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    webauthn_rp_name: str = "Maxx"
    webauthn_rp_id: str = ""  # defaults to the host of PUBLIC_BASE_URL
    trust_proxy_headers: bool = True
    admin_emails: str = ""
    email_mode: str = "log"
    email_from: str = "Maxx <no-reply@maxx.local>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    # common = personal + work/school, consumers = personal only, organizations, or a tenant id.
    microsoft_tenant: str = "common"
    apple_client_id: str = ""  # the Services ID, e.g. com.example.maxx.web
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""  # the .p8 contents; \n escapes are accepted
    # Provider endpoints are overridable so the flow can be exercised against a local stand-in.
    google_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://openidconnect.googleapis.com/v1/userinfo"
    github_authorize_url: str = "https://github.com/login/oauth/authorize"
    github_token_url: str = "https://github.com/login/oauth/access_token"
    github_user_url: str = "https://api.github.com/user"
    github_emails_url: str = "https://api.github.com/user/emails"
    google_jwks_url: str = "https://www.googleapis.com/oauth2/v3/certs"
    microsoft_authorize_url: str = (
        "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    )
    microsoft_token_url: str = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    microsoft_jwks_url: str = "https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
    microsoft_userinfo_url: str = "https://graph.microsoft.com/oidc/userinfo"
    apple_authorize_url: str = "https://appleid.apple.com/auth/authorize"
    apple_token_url: str = "https://appleid.apple.com/auth/token"
    apple_jwks_url: str = "https://appleid.apple.com/auth/keys"
    scan_rate_anonymous_per_hour: int = Field(default=30, ge=1)
    scan_rate_user_per_hour: int = Field(default=120, ge=1)
    match_rate_per_hour: int = Field(default=120, ge=1)
    bloc_actions_per_hour: int = Field(default=10, ge=1)  # Bloc creations and starts per person
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    @field_validator("demo_tools", "docs_enabled", mode="before")
    @classmethod
    def _blank_is_default(cls, value):
        # Left empty (as in .env.example) means "decide by environment".
        return None if isinstance(value, str) and not value.strip() else value


settings = Settings()
