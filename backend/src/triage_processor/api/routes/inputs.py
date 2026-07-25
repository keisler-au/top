from fastapi import APIRouter, Request, status

from triage_processor.api.schemas import InputCreate, InputResponse

router = APIRouter(prefix="/inputs", tags=["inputs"])


@router.post(
    "",
    response_model=InputResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_input(
    payload: InputCreate,
    request: Request,
) -> InputResponse:
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
