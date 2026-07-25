import json

import httpx


class StructuredChatClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 120,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    async def complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
    ) -> dict[str, object]:
        response = await self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("LLM response content must be a string")
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end < start:
            raise ValueError("LLM response did not contain a JSON object")

        parsed = json.loads(content[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("LLM response must contain a JSON object")
        return parsed

    async def close(self) -> None:
        await self._client.aclose()
