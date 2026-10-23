from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://maxx:maxx_local@127.0.0.1:55432/maxx"
    model_rates_json: str = "{}"
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
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")


settings = Settings()
