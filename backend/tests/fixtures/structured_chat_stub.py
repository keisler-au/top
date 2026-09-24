"""Deterministic OpenAI-compatible chat fixture for the Compose journey.

The acceptance stack uses a real Ollama embedding service.  Chat responses are
fixed so the test measures service wiring and the durable taxonomy lifecycle,
not the sampling behaviour of a particular local chat-model build.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


def _response_for(system_prompt: str, user_content: str) -> dict[str, object]:
    if system_prompt.startswith("You classify submitted text"):
        return {"eligible": True, "segments": []}

    payload = json.loads(user_content)
    if system_prompt.startswith("Name one evidence cluster"):
        representatives = payload["representative_evidence"]
        answer = representatives[0]["answer_text"]
        if "bus" in answer.casefold():
            return {
                "name": "Rural bus frequency",
                "description": "More frequent buses for rural villages.",
            }
        return {
            "name": "Neighbourhood park lighting",
            "description": "Brighter lighting in neighbourhood parks.",
        }

    if system_prompt.startswith("Infer a higher-order theme"):
        topic_ids = [topic["id"] for topic in payload["topics"]]
        return {
            "create_theme": True,
            "name": f"Community services {topic_ids[0]}",
            "description": "Community service improvements.",
            "rationale": "The selected topic describes a requested service improvement.",
            "topic_revision_ids": topic_ids,
        }

    raise ValueError("unsupported structured-chat prompt")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path != "/healthz":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            messages = request["messages"]
            result = _response_for(messages[0]["content"], messages[1]["content"])
            body = json.dumps(
                {"choices": [{"message": {"content": json.dumps(result)}}]}
            ).encode()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            body = json.dumps({"error": type(error).__name__}).encode()
            self.send_response(422)
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
