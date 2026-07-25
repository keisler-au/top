import json
import unittest

import httpx

from triage_processor.clients.llm import StructuredChatClient


class StructuredChatClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_consistent_json_request_and_parses_fenced_response(self):
        captured = {}

        def handler(request):
            captured["path"] = request.url.path
            captured["authorization"] = request.headers.get("authorization")
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '```json\n{"eligible": true}\n```'
                            }
                        }
                    ]
                },
            )

        client = StructuredChatClient(
            base_url="http://ollama.test/v1",
            model="local-model",
            api_key="secret",
            transport=httpx.MockTransport(handler),
        )
        try:
            result = await client.complete(
                system_prompt="System",
                user_content="Input",
            )
        finally:
            await client.close()

        self.assertEqual(result, {"eligible": True})
        self.assertEqual(captured["path"], "/v1/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer secret")
        self.assertEqual(captured["body"]["model"], "local-model")
        self.assertEqual(
            captured["body"]["response_format"],
            {"type": "json_object"},
        )

    async def test_rejects_non_object_json(self):
        def handler(request):
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "[1, 2]"}}]},
            )

        client = StructuredChatClient(
            base_url="http://ollama.test/v1",
            model="local-model",
            transport=httpx.MockTransport(handler),
        )
        try:
            with self.assertRaisesRegex(ValueError, "JSON object"):
                await client.complete(
                    system_prompt="System",
                    user_content="Input",
                )
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
