"""Black-box assertions for the disposable taxonomy Compose journey."""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.request

import asyncpg


API_BASE_URL = os.getenv("JOURNEY_API_BASE_URL", "http://api:8000")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:journey-only@postgres:5432/triage_journey"
)


def create_input(text: str, sequence: int) -> None:
    request = urllib.request.Request(
        f"{API_BASE_URL}/inputs",
        data=json.dumps(
            {
                "original_text": text,
                "source": "taxonomy-compose-journey",
                "source_record_key": f"journey-{sequence}",
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 201:
            raise AssertionError(f"input creation returned HTTP {response.status}")


async def snapshot(connection: asyncpg.Connection) -> dict[str, object]:
    run = await connection.fetchrow(
        """
        SELECT id, status, snapshot_evidence_count
        FROM taxonomy_runs
        ORDER BY id DESC
        LIMIT 1
        """
    )
    if run is None:
        return {"run": None}
    stages = await connection.fetch(
        """
        SELECT stage, status, attempt
        FROM taxonomy_run_stages
        WHERE taxonomy_run_id = $1
        ORDER BY id
        """,
        run["id"],
    )
    attestation = await connection.fetchrow(
        """
        SELECT gate_passed, failures
        FROM taxonomy_release_attestations
        WHERE taxonomy_run_id = $1
        """,
        run["id"],
    )
    return {
        "run": dict(run),
        "inputs": await connection.fetchval(
            "SELECT count(*) FROM original_inputs WHERE status='ready_for_analysis'"
        ),
        "embeddings": await connection.fetchval("SELECT count(*) FROM input_embeddings"),
        "stages": [dict(row) for row in stages],
        "attestation": dict(attestation) if attestation else None,
        "published": await connection.fetchval(
            "SELECT count(*) FROM taxonomy_runs WHERE status='published'"
        ),
        "automatic_decisions": await connection.fetchval(
            """
            SELECT count(*) FROM taxonomy_automation_decisions
            WHERE taxonomy_run_id = $1 AND status='snapshotted'
            """,
            run["id"],
        ),
    }


async def main() -> None:
    texts = [
        "More frequent buses for rural villages.",
        "More frequent buses for rural villages.",
        "More frequent buses for rural villages.",
        "Brighter lighting in neighbourhood parks.",
        "Brighter lighting in neighbourhood parks.",
        "Brighter lighting in neighbourhood parks.",
    ]
    for sequence, value in enumerate(texts, start=1):
        create_input(value, sequence)

    connection = await asyncpg.connect(DATABASE_URL)
    deadline = time.monotonic() + 480
    state: dict[str, object] = {"run": None}
    try:
        while time.monotonic() < deadline:
            state = await snapshot(connection)
            run = state.get("run")
            if isinstance(run, dict) and run["status"] in {
                "published",
                "failed",
                "ready_for_review",
            }:
                break
            await asyncio.sleep(1)
    finally:
        await connection.close()

    print(json.dumps(state, default=str, sort_keys=True))
    run = state.get("run")
    assert isinstance(run, dict), "automation did not create a taxonomy run"
    assert state["inputs"] == 6, "both evidence workers did not finish all inputs"
    assert state["embeddings"] == 6, "Ollama embeddings were not persisted"
    assert run["snapshot_evidence_count"] == 6, "candidate membership is incomplete"
    assert len(state["stages"]) == 7, "the complete taxonomy stage chain was not created"
    assert all(stage["status"] == "completed" for stage in state["stages"]), state
    assert state["attestation"] == {"gate_passed": True, "failures": []}, state
    assert run["status"] == "published" and state["published"] == 1, state
    assert state["automatic_decisions"] == 1, state


if __name__ == "__main__":
    asyncio.run(main())
