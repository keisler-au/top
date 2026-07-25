import argparse
import asyncio
import logging
import math
import os
from collections.abc import Sequence
from typing import Protocol

import asyncpg
import httpx

from app.config import DATABASE_URL

LOGGER = logging.getLogger(__name__)


class TextEmbedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OllamaEmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 120,
        dimensions: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        request_body: dict[str, object] = {
            "model": self._model,
            "input": list(texts),
            "truncate": False,
        }
        if self._dimensions is not None:
            request_body["dimensions"] = self._dimensions

        response = await self._client.post("/api/embed", json=request_body)
        response.raise_for_status()
        response_body = response.json()

        embeddings = response_body.get("embeddings")
        if not isinstance(embeddings, list):
            raise ValueError("Ollama response did not contain an embeddings array")
        if len(embeddings) != len(texts):
            raise ValueError(
                "Ollama returned a different number of embeddings than inputs"
            )

        return [_validate_vector(vector) for vector in embeddings]

    async def close(self) -> None:
        await self._client.aclose()


def _validate_vector(vector: object) -> list[float]:
    if not isinstance(vector, list) or not vector:
        raise ValueError("Ollama returned an empty or invalid embedding")

    validated: list[float] = []
    for component in vector:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise ValueError("embedding components must be numbers")
        value = float(component)
        if not math.isfinite(value):
            raise ValueError("embedding components must be finite")
        validated.append(value)
    return validated


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
            validated = _validate_vector(vector)
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
) -> bool:
    if not embedding_model.strip():
        raise ValueError("embedding_model cannot be blank")

    async with pool.acquire() as connection:
        async with connection.transaction():
            original = await connection.fetchrow(
                """
                SELECT id, original_text
                FROM original_inputs
                WHERE status = 'ready_for_embedding'
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
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

            texts = [original["original_text"]]
            texts.extend(segment["segment_text"] for segment in segments)
            embeddings = await _embed_in_batches(embedder, texts, batch_size)

            embedding_rows = [
                (
                    original["id"],
                    None,
                    _to_pgvector(embeddings[0]),
                    embedding_model,
                )
            ]
            embedding_rows.extend(
                (
                    None,
                    segment["id"],
                    _to_pgvector(vector),
                    embedding_model,
                )
                for segment, vector in zip(
                    segments,
                    embeddings[1:],
                    strict=True,
                )
            )

            await connection.executemany(
                """
                INSERT INTO input_embeddings (
                    original_input_id,
                    segment_input_id,
                    embedding,
                    embedding_model
                )
                VALUES ($1, $2, $3::vector, $4)
                """,
                embedding_rows,
            )
            await connection.execute(
                """
                UPDATE original_inputs
                SET status = 'ready_for_analysis'
                WHERE id = $1
                """,
                original["id"],
            )

            LOGGER.info(
                "Embedded input %s: vectors=%s dimensions=%s",
                original["id"],
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

    embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "embeddinggemma")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    embedder = OllamaEmbeddingClient(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        model=embedding_model,
        timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
        dimensions=dimensions,
    )

    try:
        while True:
            try:
                processed = await process_next_input(
                    pool,
                    embedder,
                    batch_size=batch_size,
                    embedding_model=embedding_model,
                )
            except Exception:
                LOGGER.exception("Embedding generation failed")
                if once:
                    raise
                await asyncio.sleep(poll_interval)
                continue

            if once or not processed:
                if once:
                    return
                await asyncio.sleep(poll_interval)
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

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(
        run_worker(
            once=args.once,
            poll_interval=args.poll_interval,
            batch_size=args.batch_size,
        )
    )


if __name__ == "__main__":
    main()
