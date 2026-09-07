from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from time import perf_counter

import asyncpg
from fastapi import FastAPI

from triage_processor.api.routes.articles import router as articles_router
from triage_processor.api.routes.dashboard import router as dashboard_router
from triage_processor.api.routes.form_sources import router as form_sources_router
from triage_processor.api.routes.generation import router as generation_router
from triage_processor.api.routes.inputs import router as inputs_router
from triage_processor.api.routes.operations import router as operations_router
from triage_processor.config import DATABASE_URL
from triage_processor.observability import configure_logging

configure_logging()
LOGGER = logging.getLogger("triage_processor.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db_pool = await asyncpg.create_pool(DATABASE_URL)
    try:
        yield
    finally:
        await app.state.db_pool.close()


app = FastAPI(
    title="Triage Organisation Processor",
    lifespan=lifespan,
)
app.include_router(articles_router)
app.include_router(generation_router)
app.include_router(dashboard_router)
app.include_router(form_sources_router)
app.include_router(inputs_router)
app.include_router(operations_router)


@app.middleware("http")
async def log_request(request, call_next):
    started = perf_counter()
    response = await call_next(request)
    LOGGER.info(
        "request complete",
        extra={
            "event": "api_request",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((perf_counter() - started) * 1000),
        },
    )
    return response


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> dict[str, str]:
    """Container health endpoint; startup has already established the DB pool."""
    return {"status": "ok"}
