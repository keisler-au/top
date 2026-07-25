import unittest

import httpx

from triage_processor.clients.ollama import OllamaEmbeddingClient
from triage_processor.workers.embeddings import (
    _embed_in_batches,
    _to_pgvector,
    process_next_input,
)


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, original, segments=None):
        self.original = original
        self.segments = segments or []
        self.embedding_rows = []
        self.executed = []
        self.fetchrow_values = []

    def transaction(self):
        return AsyncContext(None)

    async def fetchrow(self, query, *values):
        self.fetchrow_values.append(values)
        return self.original

    async def fetch(self, query, input_id):
        return self.segments

    async def executemany(self, query, values):
        self.embedding_rows.extend(values)

    async def execute(self, query, *values):
        self.executed.append(values)


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class FakeEmbedder:
    def __init__(self, vectors_by_text=None, fail_on_call=None):
        self.vectors_by_text = vectors_by_text or {}
        self.fail_on_call = fail_on_call
        self.calls = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("Ollama unavailable")
        return [self.vectors_by_text[text] for text in texts]


class EmbeddingsWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_ollama_client_uses_native_batch_endpoint(self):
        captured = {}

        def handler(request):
            captured["path"] = request.url.path
            captured["body"] = request.read().decode()
            return httpx.Response(
                200,
                json={"embeddings": [[1.0, 0.0], [0.0, 1.0]]},
            )

        client = OllamaEmbeddingClient(
            base_url="http://ollama.test",
            model="embeddinggemma",
            dimensions=2,
            transport=httpx.MockTransport(handler),
        )
        try:
            vectors = await client.embed(["First", "Second"])
        finally:
            await client.close()

        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(captured["path"], "/api/embed")
        self.assertIn('"truncate":false', captured["body"])
        self.assertIn('"dimensions":2', captured["body"])

    async def test_embeds_original_and_segments_in_small_batches(self):
        connection = FakeConnection(
            {"id": 10, "original_text": "Full input"},
            [
                {"id": 21, "segment_text": "First segment"},
                {"id": 22, "segment_text": "Second segment"},
                {"id": 23, "segment_text": "Third segment"},
            ],
        )
        embedder = FakeEmbedder(
            {
                "Full input": [1.0, 2.0],
                "First segment": [3.0, 4.0],
                "Second segment": [5.0, 6.0],
                "Third segment": [7.0, 8.0],
            }
        )

        processed = await process_next_input(
            FakePool(connection),
            embedder,
            batch_size=2,
            embedding_model="embeddinggemma",
            input_id=10,
        )

        self.assertTrue(processed)
        self.assertEqual(connection.fetchrow_values, [(10,)])
        self.assertEqual(
            embedder.calls,
            [
                ["Full input", "First segment"],
                ["Second segment", "Third segment"],
            ],
        )
        self.assertEqual(
            connection.embedding_rows,
            [
                (10, None, "[1,2]", "embeddinggemma"),
                (None, 21, "[3,4]", "embeddinggemma"),
                (None, 22, "[5,6]", "embeddinggemma"),
                (None, 23, "[7,8]", "embeddinggemma"),
            ],
        )
        self.assertEqual(connection.executed, [(10,)])

    async def test_input_without_segments_gets_original_embedding(self):
        connection = FakeConnection({"id": 11, "original_text": "One topic"})
        embedder = FakeEmbedder({"One topic": [0.25, -0.5]})

        processed = await process_next_input(
            FakePool(connection),
            embedder,
            batch_size=4,
            embedding_model="embeddinggemma",
        )

        self.assertTrue(processed)
        self.assertEqual(
            connection.embedding_rows,
            [(11, None, "[0.25,-0.5]", "embeddinggemma")],
        )
        self.assertEqual(connection.executed, [(11,)])

    async def test_no_ready_input_does_nothing(self):
        connection = FakeConnection(None)
        embedder = FakeEmbedder(fail_on_call=1)

        processed = await process_next_input(
            FakePool(connection),
            embedder,
            batch_size=2,
            embedding_model="embeddinggemma",
        )

        self.assertFalse(processed)
        self.assertEqual(embedder.calls, [])
        self.assertEqual(connection.embedding_rows, [])
        self.assertEqual(connection.executed, [])

    async def test_ollama_failure_produces_no_database_writes(self):
        connection = FakeConnection(
            {"id": 12, "original_text": "Full"},
            [{"id": 24, "segment_text": "Segment"}],
        )
        embedder = FakeEmbedder(
            {
                "Full": [1.0, 2.0],
                "Segment": [3.0, 4.0],
            },
            fail_on_call=2,
        )

        with self.assertRaises(RuntimeError):
            await process_next_input(
                FakePool(connection),
                embedder,
                batch_size=1,
                embedding_model="embeddinggemma",
            )

        self.assertEqual(connection.embedding_rows, [])
        self.assertEqual(connection.executed, [])

    async def test_rejects_inconsistent_dimensions(self):
        embedder = FakeEmbedder(
            {
                "First": [1.0, 2.0],
                "Second": [3.0],
            }
        )

        with self.assertRaisesRegex(ValueError, "dimensions"):
            await _embed_in_batches(
                embedder,
                ["First", "Second"],
                batch_size=1,
            )

    def test_pgvector_serialization(self):
        self.assertEqual(_to_pgvector([0.1, -2.5, 3.0]), "[0.10000000000000001,-2.5,3]")


if __name__ == "__main__":
    unittest.main()
