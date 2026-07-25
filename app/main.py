from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

import asyncpg
from fastapi import FastAPI, Request, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.config import DATABASE_URL

RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class InputCreate(BaseModel):
    original_text: RequiredText
    source: RequiredText


class InputResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_text: str
    source: str
    status: str
    topic: str | None
    created_at: datetime


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


@app.post(
    "/inputs",
    response_model=InputResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_input(payload: InputCreate, request: Request) -> InputResponse:
    async with request.app.state.db_pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            INSERT INTO original_inputs (original_text, source)
            VALUES ($1, $2)
            RETURNING id, original_text, source, status, topic, created_at
            """,
            payload.original_text,
            payload.source,
        )

    return InputResponse.model_validate(dict(row))
