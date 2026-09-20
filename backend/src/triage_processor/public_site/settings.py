"""Validated, deployment-owned settings for the public website."""
from dataclasses import dataclass
import os
from urllib.parse import urlparse


DEFAULT_ORIGIN = "http://localhost:8080"
DEFAULT_NAME = "Evidence-led insights"
MAX_TEXT_LENGTH = 300


@dataclass(frozen=True)
class PublicSiteSettings:
    origin: str
    name: str
    description: str | None

    @classmethod
    def from_env(cls) -> "PublicSiteSettings":
        raw_origin = os.getenv("PUBLIC_SITE_ORIGIN", DEFAULT_ORIGIN).strip()
        parsed = urlparse(raw_origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("PUBLIC_SITE_ORIGIN must be an absolute http(s) origin without a path, query, or credentials")
        name = os.getenv("PUBLIC_SITE_NAME", DEFAULT_NAME).strip()
        description = os.getenv("PUBLIC_SITE_DESCRIPTION", "").strip() or None
        if not name or len(name) > MAX_TEXT_LENGTH:
            raise ValueError(f"PUBLIC_SITE_NAME must contain 1 to {MAX_TEXT_LENGTH} characters")
        if description is not None and len(description) > MAX_TEXT_LENGTH:
            raise ValueError(f"PUBLIC_SITE_DESCRIPTION must contain at most {MAX_TEXT_LENGTH} characters")
        return cls(origin=raw_origin.rstrip("/"), name=name, description=description)
