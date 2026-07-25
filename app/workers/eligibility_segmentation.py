import argparse
import asyncio
import logging
import os
from typing import Annotated, Protocol

import asyncpg
from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.config import DATABASE_URL
from app.llm import StructuredChatClient

LOGGER = logging.getLogger(__name__)

SegmentText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

SYSTEM_PROMPT = """\
You classify submitted text for a topic-organising system.

Return JSON with this exact shape:
{"eligible": true, "segments": ["first topical segment", "second topical segment"]}

Eligibility:
- Eligible text contains meaningful content that can be organised by topic.
- Ineligible text is spam, meaningless, purely administrative, or has no useful
  topical content.

Segmentation:
- Only segment eligible text when it contains two or more distinct topics.
- Preserve the meaning and wording of the source text.
- Segments must be self-contained, non-overlapping, and follow source order.
- Return an empty segments array when no split is needed or the text is ineligible.
- Return JSON only, without Markdown or commentary.
"""


class SegmentationDecision(BaseModel):
    eligible: bool
    segments: list[SegmentText] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_segments(self) -> "SegmentationDecision":
        if not self.eligible and self.segments:
            raise ValueError("ineligible inputs cannot contain segments")
        if len(self.segments) == 1:
            raise ValueError("segmentation requires at least two segments")
        if len(set(self.segments)) != len(self.segments):
            raise ValueError("segments must be unique")
        return self


class EligibilitySegmenter(Protocol):
    async def classify(self, original_text: str) -> SegmentationDecision: ...


class LocalLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        self._client = StructuredChatClient(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout=timeout_seconds,
        )

    async def classify(self, original_text: str) -> SegmentationDecision:
        result = await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_content=original_text,
        )
        return SegmentationDecision.model_validate(result)

    async def close(self) -> None:
        await self._client.aclose()
async def process_next_input(
    pool: asyncpg.Pool,
    segmenter: EligibilitySegmenter,
) -> bool:
    async with pool.acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                SELECT id, original_text
                FROM original_inputs
                WHERE status = 'new'
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            if row is None:
                return False

            input_id = row["id"]
            decision = await segmenter.classify(row["original_text"])

            if decision.eligible and decision.segments:
                await connection.executemany(
                    """
                    INSERT INTO segment_inputs (
                        original_input_id,
                        segment_order,
                        segment_text
                    )
                    VALUES ($1, $2, $3)
                    """,
                    [
                        (input_id, order, segment)
                        for order, segment in enumerate(decision.segments)
                    ],
                )

            next_status = (
                "ready_for_embedding" if decision.eligible else "ineligible"
            )
            await connection.execute(
                """
                UPDATE original_inputs
                SET status = $2
                WHERE id = $1
                """,
                input_id,
                next_status,
            )

            LOGGER.info(
                "Processed input %s: status=%s segments=%s",
                input_id,
                next_status,
                len(decision.segments),
            )
            return True


async def run_worker(*, once: bool, poll_interval: float) -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    segmenter = LocalLLMClient(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        model=os.getenv("LLM_MODEL", "llama3.2"),
        api_key=os.getenv("LLM_API_KEY"),
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
    )

    try:
        while True:
            try:
                processed = await process_next_input(pool, segmenter)
            except Exception:
                LOGGER.exception("Eligibility and segmentation failed")
                if once:
                    raise
                await asyncio.sleep(poll_interval)
                continue

            if once or not processed:
                if once:
                    return
                await asyncio.sleep(poll_interval)
    finally:
        await segmenter.close()
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify and segment new original inputs."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one input and exit.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("WORKER_POLL_INTERVAL", "2")),
        help="Seconds to wait when no work is available or processing fails.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker(once=args.once, poll_interval=args.poll_interval))


if __name__ == "__main__":
    main()
