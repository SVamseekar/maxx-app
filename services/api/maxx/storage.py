from functools import lru_cache

from maxx.config import settings
from maxx.negotiate.store import BlocStore


@lru_cache
def get_store():
    if not settings.database_url.startswith("postgresql+psycopg://"):
        raise ValueError("Application DATABASE_URL must use PostgreSQL with Psycopg.")
    return BlocStore(settings.database_url, initialize=False)
