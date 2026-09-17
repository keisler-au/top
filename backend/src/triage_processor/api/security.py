"""Fail-closed authentication and durable rate limiting for operator APIs."""
from __future__ import annotations

from hashlib import sha256
import hmac
import os

from fastapi import HTTPException, Request, status


def _token(name: str) -> str:
    return os.getenv(name, "").strip()


def _presented_token(request: Request) -> str:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def _limit() -> int:
    try:
        value = int(os.getenv("OPERATIONS_RATE_LIMIT_REQUESTS", "30"))
    except ValueError as error:
        raise RuntimeError("OPERATIONS_RATE_LIMIT_REQUESTS must be an integer") from error
    if value < 1 or value > 10_000:
        raise RuntimeError("OPERATIONS_RATE_LIMIT_REQUESTS must be between 1 and 10000")
    return value


def _window_seconds() -> int:
    try:
        value = int(os.getenv("OPERATIONS_RATE_LIMIT_WINDOW_SECONDS", "60"))
    except ValueError as error:
        raise RuntimeError("OPERATIONS_RATE_LIMIT_WINDOW_SECONDS must be an integer") from error
    if value < 1 or value > 86_400:
        raise RuntimeError("OPERATIONS_RATE_LIMIT_WINDOW_SECONDS must be between 1 and 86400")
    return value


async def require_operator(request: Request, *, mutation: bool) -> None:
    """Authorize a review or mutation token and consume a durable allowance."""
    mutation_token = _token("TAXONOMY_MUTATION_TOKEN")
    review_token = _token("TAXONOMY_REVIEW_TOKEN")
    if (mutation and not mutation_token) or (not mutation and not (mutation_token or review_token)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "operations_auth_unconfigured"},
        )

    presented = _presented_token(request)
    allowed = hmac.compare_digest(presented, mutation_token)
    if not mutation:
        allowed = allowed or hmac.compare_digest(presented, review_token)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "operations_unauthorized"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    actor = sha256(presented.encode()).hexdigest()
    scope = "taxonomy_mutation" if mutation else "operations_read"
    maximum_requests = _limit()
    window_seconds = _window_seconds()
    async with request.app.state.db_pool.acquire() as connection:
        count = await connection.fetchval(
            "SELECT consume_operations_rate_limit($1, $2, $3, $4)",
            scope, actor, window_seconds, maximum_requests,
        )
    if count > maximum_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "operations_rate_limited"},
        )
