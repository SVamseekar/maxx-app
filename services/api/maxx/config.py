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
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")


settings = Settings()
