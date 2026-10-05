from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError

from maxx.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine.dispose()


app = FastAPI(title="Maxx API", version="0.1.0", lifespan=lifespan)


def get_connection() -> Iterator[Connection]:
    with engine.connect() as connection:
        yield connection


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    # Connection errors may contain credentials; never expose them to clients.
    return JSONResponse(
        status_code=503,
        content={"status": "unavailable", "service": "maxx-api", "database": "unavailable"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: the API process works, regardless of database availability."""
    return {"status": "ok", "service": "maxx-api"}


@app.get("/health/ready", responses={503: {"description": "Database unavailable"}})
def ready(connection: Annotated[Connection, Depends(get_connection)]) -> dict[str, str]:
    """Readiness: verify the configured database with a real query."""
    connection.execute(text("SELECT 1"))
    return {"status": "ok", "service": "maxx-api", "database": "ok"}
