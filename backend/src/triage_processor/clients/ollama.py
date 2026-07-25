import math
from collections.abc import Sequence

import httpx


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
            raise ValueError(
                "Ollama response did not contain an embeddings array"
            )
        if len(embeddings) != len(texts):
            raise ValueError(
                "Ollama returned a different number of embeddings than inputs"
            )

        return [validate_vector(vector) for vector in embeddings]

    async def close(self) -> None:
        await self._client.aclose()


def validate_vector(vector: object) -> list[float]:
    if not isinstance(vector, list) or not vector:
        raise ValueError("Ollama returned an empty or invalid embedding")

    validated: list[float] = []
    for component in vector:
        if isinstance(component, bool) or not isinstance(
            component,
            (int, float),
        ):
            raise ValueError("embedding components must be numbers")
        value = float(component)
        if not math.isfinite(value):
            raise ValueError("embedding components must be finite")
        validated.append(value)
    return validated
