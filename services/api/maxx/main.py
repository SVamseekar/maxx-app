import asyncio
import logging
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
    from maxx.config import settings
    from maxx.negotiate.routes import get_runtime, peek_runtime

    worker = None
    if settings.worker_enabled:
        runtime = get_runtime()

        async def dispatch():
            while True:
                try:
                    await runtime.tick()
                except SQLAlchemyError:
                    # Never log connection exceptions, which may include credentials.
                    logging.getLogger(__name__).warning(
                        "Job dispatcher database unavailable; retrying."
                    )
                    await asyncio.sleep(5)
                    continue
                await asyncio.sleep(1)

        worker = asyncio.create_task(dispatch())
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        runtime = peek_runtime()
        if runtime is not None:
            await runtime.close()
        engine.dispose()


from maxx.config import settings as _settings  # noqa: E402
from maxx.hardening import (  # noqa: E402
    HardeningMiddleware,
    enforce_configuration,
    install_log_redaction,
)

enforce_configuration()
install_log_redaction()
_docs = (
    _settings.docs_enabled
    if _settings.docs_enabled is not None
    else _settings.environment != "production"
)
app = FastAPI(
    title="Maxx API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _docs else None,
)
if _settings.allowed_hosts.strip() not in {"", "*"}:
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[h.strip() for h in _settings.allowed_hosts.split(",") if h.strip()],
    )
app.add_middleware(HardeningMiddleware)


def get_connection() -> Iterator[Connection]:
    with engine.connect() as connection:
        yield connection


from maxx.auth.deps import CodedError  # noqa: E402


@app.exception_handler(CodedError)
async def coded_error(request: Request, exc: CodedError) -> JSONResponse:
    return JSONResponse({"detail": exc.detail, "code": exc.code}, status_code=exc.status_code)


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


from maxx.scan_routes import router  # noqa: E402

app.include_router(router)

from maxx.negotiate.routes import router as bloc_router  # noqa: E402

app.include_router(bloc_router)

from maxx.transparency import router as transparency_router  # noqa: E402

app.include_router(transparency_router)

from maxx.auth import routes as auth_routes  # noqa: E402
from maxx.auth import routes_security  # noqa: E402

app.include_router(auth_routes.router, prefix="/auth")
app.include_router(auth_routes.form_post_router, prefix="/auth")
app.include_router(routes_security.router, prefix="/auth")
app.include_router(auth_routes.me_router)

from maxx.money import routes as money_routes  # noqa: E402

app.include_router(money_routes.router)
app.include_router(money_routes.hooks)
app.include_router(money_routes.checkout_router)
app.include_router(money_routes.plus_router)

from maxx.sellers import routes as seller_routes  # noqa: E402

app.include_router(seller_routes.router)

from maxx.admin import routes as admin_routes  # noqa: E402
from maxx.fulfilment import routes as fulfilment_routes  # noqa: E402

app.include_router(fulfilment_routes.router)
app.include_router(admin_routes.router)
