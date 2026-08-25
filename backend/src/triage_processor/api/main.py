from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from triage_processor.api.routes.articles import router as articles_router
from triage_processor.api.routes.dashboard import router as dashboard_router
from triage_processor.api.routes.form_sources import router as form_sources_router
from triage_processor.api.routes.generation import router as generation_router
from triage_processor.api.routes.inputs import router as inputs_router
from triage_processor.config import DATABASE_URL


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
