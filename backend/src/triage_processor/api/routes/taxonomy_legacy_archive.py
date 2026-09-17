"""Read-only, bounded audit access to the immutable legacy taxonomy archive."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from triage_processor.api.security import require_operator

router = APIRouter(prefix="/taxonomy-legacy-archive", tags=["taxonomy archive"])

# These are archive-only values: no raw input text, prompt payload, or model
# response is part of any selectable relation.
_TABLES = {
    "input_topics": "original_input_id",
    "segment_topics": "segment_input_id",
    "themes": "theme_id",
    "theme_topics": "theme_id",
    "theme_suggestions": "suggestion_id",
    "suggestion_existing_themes": "suggestion_id",
    "suggestion_topics": "suggestion_id",
    "suggestion_evidence": "suggestion_evidence_id",
    "assignment_attempts": "assignment_attempt_id",
    "rollout_reports": "taxonomy_run_id",
}


@router.get("")
async def archive_manifest(request: Request) -> dict[str, object]:
    """Return archive integrity metadata; only a review/operator token may read it."""
    await require_operator(request, mutation=False)
    async with request.app.state.db_pool.acquire() as connection:
        row = await connection.fetchrow("""
            SELECT format_version, exported_at, source_cutoff, table_counts,
                   table_hashes, archive_sha256
            FROM taxonomy_legacy_archive.exports
            ORDER BY id DESC LIMIT 1
        """)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "legacy_archive_unavailable"})
    return dict(row)


@router.get("/{table_name}")
async def archive_rows(
    table_name: str, request: Request, after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    """Page one safe archive relation by its immutable legacy identifier."""
    await require_operator(request, mutation=False)
    key = _TABLES.get(table_name)
    if key is None:
        raise HTTPException(status_code=404, detail={"code": "legacy_archive_table_not_found"})
    async with request.app.state.db_pool.acquire() as connection:
        rows = await connection.fetch(
            f"SELECT * FROM taxonomy_legacy_archive.{table_name} "
            f"WHERE {key} > $1 ORDER BY {key} LIMIT $2", after_id, limit,
        )
    values = [dict(row) for row in rows]
    return {
        "table": table_name,
        "rows": values,
        "next_after_id": values[-1][key] if len(values) == limit else None,
    }
