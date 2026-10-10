import argparse
import asyncio
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import asyncpg

from triage_processor.clients.ollama import (
    OllamaEmbeddingClient,
    validate_vector,
)
from triage_processor.config import DATABASE_URL
from triage_processor.observability import configure_logging
from triage_processor.job_queue import (
    Job,
    QueueSettings,
    complete_job_in_transaction,
    require_job_lease,
    run_job_loop,
)

LOGGER = logging.getLogger(__name__)


class TextEmbedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class EmbeddingTarget:
    segment_id: int | None
    text: str


@dataclass(frozen=True)
class EmbeddingWork:
    input_id: int
    original_text: str
    question_id: int
    question_text: str
    targets: tuple[EmbeddingTarget, ...]


def build_embedding_input(
    *,
    answer_text: str,
    question_text: str | None,
) -> str:
    if question_text is None:
        return answer_text
    return f"Question: {question_text}\nAnswer: {answer_text}"


def _to_pgvector(vector: Sequence[float]) -> str:
    return "[" + ",".join(format(value, ".17g") for value in vector) + "]"


async def _embed_in_batches(
    embedder: TextEmbedder,
    texts: Sequence[str],
    batch_size: int,
) -> list[list[float]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    embeddings: list[list[float]] = []
    expected_dimensions: int | None = None

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors = await embedder.embed(batch)
        if len(vectors) != len(batch):
            raise ValueError(
                "embedding provider returned a different number of vectors than texts"
            )

        for vector in vectors:
            validated = validate_vector(vector)
            dimensions = len(validated)
            if expected_dimensions is None:
                expected_dimensions = dimensions
            elif dimensions != expected_dimensions:
                raise ValueError("embedding dimensions must be consistent")
            embeddings.append(validated)

    return embeddings


async def process_next_input(
    pool: asyncpg.Pool,
    embedder: TextEmbedder,
    *,
    batch_size: int,
    embedding_model: str,
    input_id: int | None = None,
    job: Job | None = None,
) -> bool:
    if not embedding_model.strip():
        raise ValueError("embedding_model cannot be blank")

    async with pool.acquire() as connection:
        if job is not None:
            original = await connection.fetchrow(
                """
                SELECT inputs.id, inputs.original_text, inputs.question_id,
                       questions.question_text
                FROM worker_jobs AS jobs
                JOIN original_inputs AS inputs ON inputs.id = jobs.original_input_id
                JOIN questions ON questions.id = inputs.question_id
                WHERE jobs.id = $1 AND jobs.job_type = 'embeddings'
                  AND jobs.status = 'processing' AND jobs.locked_by = $2
                  AND inputs.id = $3 AND inputs.status = 'ready_for_embedding'
                """,
                job.id,
                job.locked_by,
                job.original_input_id,
            )
        elif input_id is None:
            original = await connection.fetchrow(
                    """
                    SELECT
                        inputs.id,
                        inputs.original_text,
                        inputs.question_id,
                        questions.question_text
                    FROM original_inputs AS inputs
                    JOIN questions
                        ON questions.id = inputs.question_id
                    WHERE inputs.status = 'ready_for_embedding'
                    ORDER BY inputs.id
                    LIMIT 1
                    """
                )
        else:
            original = await connection.fetchrow(
                    """
                    SELECT
                        inputs.id,
                        inputs.original_text,
                        inputs.question_id,
                        questions.question_text
                    FROM original_inputs AS inputs
                    JOIN questions
                        ON questions.id = inputs.question_id
                    WHERE inputs.id = $1
                        AND inputs.status = 'ready_for_embedding'
                    """,
                    input_id,
                )
        if original is None:
            return False
        segments = await connection.fetch(
                """
                SELECT id, segment_text
                FROM segment_inputs
                WHERE original_input_id = $1
                ORDER BY segment_order
                """,
                original["id"],
            )

    work = EmbeddingWork(
        input_id=original["id"],
        original_text=original["original_text"],
        question_id=original["question_id"],
        question_text=original["question_text"],
        targets=(EmbeddingTarget(None, original["original_text"]),)
        + tuple(EmbeddingTarget(segment["id"], segment["segment_text"]) for segment in segments),
    )
    texts = [
        build_embedding_input(answer_text=target.text, question_text=work.question_text)
        for target in work.targets
    ]
    # Ollama is called after the read connection has been released.
    embeddings = await _embed_in_batches(embedder, texts, batch_size)
    embedding_rows = [
                (
                    work.input_id if target.segment_id is None else None,
                    target.segment_id,
                    _to_pgvector(vector),
                    embedding_model,
                    "question-answer",
                )
                for target, vector in zip(work.targets, embeddings, strict=True)
            ]

    async with pool.acquire() as connection:
        async with connection.transaction():
            if job is not None:
                await require_job_lease(connection, job)
            current = await connection.fetchrow(
                """
                SELECT original_text, question_id, status
                FROM original_inputs WHERE id = $1 FOR UPDATE
                """,
                work.input_id,
            )
            if current is None or current["status"] != "ready_for_embedding":
                raise RuntimeError("input is no longer available for embedding")
            if current["original_text"] != work.original_text or current["question_id"] != work.question_id:
                raise RuntimeError("input changed during embedding")
            current_segments = await connection.fetch(
                """SELECT id, segment_text FROM segment_inputs
                   WHERE original_input_id = $1 ORDER BY segment_order""",
                work.input_id,
            )
            expected_segments = tuple(
                (target.segment_id, target.text)
                for target in work.targets
                if target.segment_id is not None
            )
            if tuple((row["id"], row["segment_text"]) for row in current_segments) != expected_segments:
                raise RuntimeError("segments changed during embedding")
            await connection.executemany(
                """
                INSERT INTO input_embeddings (
                    original_input_id,
                    segment_input_id,
                    embedding,
                    embedding_model,
                    embedding_representation
                )
                VALUES ($1, $2, $3::vector, $4, $5)
                """,
                embedding_rows,
            )
            await connection.execute(
                """
                UPDATE original_inputs
                SET status = 'ready_for_analysis'
                WHERE id = $1
                """,
                work.input_id,
            )
            if job is not None:
                await complete_job_in_transaction(connection, job)

            LOGGER.info(
                "Embedded input %s: vectors=%s dimensions=%s",
                work.input_id,
                len(embeddings),
                len(embeddings[0]),
            )
            return True


async def run_worker(
    *,
    once: bool,
    poll_interval: float,
    batch_size: int,
) -> None:
    dimensions_value = os.getenv("OLLAMA_EMBEDDING_DIMENSIONS")
    dimensions = int(dimensions_value) if dimensions_value else None
    if dimensions is not None and dimensions < 1:
        raise ValueError("OLLAMA_EMBEDDING_DIMENSIONS must be at least 1")

    embedding_model = os.getenv(
        "OLLAMA_EMBEDDING_MODEL",
        "nomic-embed-text",
    )
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    queue_settings = QueueSettings.from_env()
    embedder = OllamaEmbeddingClient(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        model=embedding_model,
        timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
        dimensions=dimensions,
    )

    try:
        async def handle(job: Job) -> bool:
            return await process_next_input(
                pool,
                embedder,
                batch_size=batch_size,
                embedding_model=embedding_model,
                input_id=job.original_input_id,
                job=job,
            )

        await run_job_loop(
            pool,
            job_type="embeddings",
            handler=handle,
            once=once,
            poll_interval=poll_interval,
            settings=queue_settings,
        )
    finally:
        await embedder.close()
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate embeddings for eligible inputs and their segments."
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
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("OLLAMA_EMBEDDING_BATCH_SIZE", "16")),
        help="Maximum number of texts sent to Ollama per request.",
    )
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")

    configure_logging()
    asyncio.run(
        run_worker(
            once=args.once,
            poll_interval=args.poll_interval,
            batch_size=args.batch_size,
        )
    )


if __name__ == "__main__":
    main()
