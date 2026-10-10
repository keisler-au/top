"""Deterministic OpenAI-compatible chat fixture for the Compose journey.

The acceptance stack uses a real Ollama embedding service.  Chat responses are
fixed so the test measures service wiring and the durable taxonomy lifecycle,
not the sampling behaviour of a particular local chat-model build.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


MODE = "partial"


def _response_for(system_prompt: str, user_content: str) -> dict[str, object]:
    if system_prompt.startswith("You classify submitted text"):
        return {"eligible": "SPAM" not in user_content, "segments": []}

    payload = json.loads(user_content)
    if system_prompt.startswith("Name one evidence cluster"):
        representatives = payload["representative_evidence"]
        answer = representatives[0]["answer_text"]
        evidence_ids = [item["evidence_id"] for item in representatives]
        if MODE == "failed" or (MODE == "partial" and "fares" in answer.casefold()):
            return {"name": "", "description": "", "evidence_ids": evidence_ids}
        if "frequent" in answer.casefold():
            return {
                "name": "Accessible transit",
                "description": "Regular connections to essential destinations.",
                "evidence_ids": evidence_ids,
            }
        return {
            "name": "Affordable travel",
            "description": "Economic access through reasonable travel costs.",
            "evidence_ids": evidence_ids,
        }

    if system_prompt.startswith("Infer an optional broader theme"):
        topic_ids = [topic["id"] for topic in payload["topics"]]
        return {
            "create_theme": True,
            "name": f"Community services {topic_ids[0]}",
            "description": "Community service improvements.",
            "rationale": "The distinct topics describe related transport access improvements.",
            "topic_revision_ids": topic_ids,
        }

    if system_prompt.startswith("Reconcile provisional topics"):
        topic_ids = [topic["id"] for topic in payload["topics"]]
        groups = []
        remaining = []
        for name in sorted({topic["name"] for topic in payload["topics"]}):
            ids = [topic["id"] for topic in payload["topics"] if topic["name"] == name]
            if len(ids) > 1:
                groups.append({"provisional_topic_ids": ids, "name": name,
                               "description": "Connections to essential destinations." if name == "Accessible transit" else "Economic access through reasonable travel costs.",
                               "rationale": "Same concept across different questions."})
            else:
                remaining.extend(ids)
        return {"groups": groups, "no_merge_topic_ids": remaining}

    if system_prompt.startswith("Write an evidence-grounded article"):
        return {"title": "Community transport insight", "standfirst": "Residents describe transport needs.",
                "sections": [{"heading": "Access", "paragraphs": ["Residents ask for better connections."],
                              "evidence_ids": [item["evidence_id"] for item in payload["evidence"]]}],
                "theme_ids": [], "topic_keys": [payload["target"]["key"]]}

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
        global MODE
        if self.path == "/fixture/mode":
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if value.get("mode") not in {"partial", "full", "failed"}:
                self.send_error(422)
                return
            MODE = value["mode"]
            self.send_response(204)
            self.end_headers()
            return
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
