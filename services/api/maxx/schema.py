"""Application tables shared by Alembic and storage; Postgres is the runtime store."""

from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, Text

metadata = MetaData()
blocs = Table(
    "bloc_documents",
    metadata,
    Column("id", String(100), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("document", Text, nullable=False),
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
