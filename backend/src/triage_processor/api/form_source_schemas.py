import re
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

RequiredText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
FORM_SOURCE_DEFAULT_SHEET = "Form Responses 1"
FORM_SOURCE_DEFAULT_INTERVAL = 60
FORM_SOURCE_MAX_INTERVAL = 86_400
SPREADSHEET_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
SPREADSHEET_URL_PATTERN = re.compile(r"/spreadsheets/d/([^/]+)")


def normalize_spreadsheet_id(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("spreadsheet_id must be non-empty")
    if "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or parsed.hostname != "docs.google.com":
            raise ValueError("spreadsheet URL must be a Google HTTPS URL")
        match = SPREADSHEET_URL_PATTERN.search(parsed.path)
        if match is None:
            raise ValueError("spreadsheet URL does not contain a spreadsheet ID")
        candidate = match.group(1)
    if not SPREADSHEET_ID_PATTERN.fullmatch(candidate):
        raise ValueError("spreadsheet_id contains unsupported characters")
    return candidate


def normalize_ignored_headers(value: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        header = item.strip()
        if not header:
            raise ValueError("ignored_headers cannot contain blank values")
        if len(header) > 500:
            raise ValueError("ignored header names cannot exceed 500 characters")
        key = header.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(header)
        if len(normalized) > 100:
            raise ValueError("ignored_headers cannot contain more than 100 values")
    return normalized


class FormSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form_id: RequiredText
    spreadsheet_id: RequiredText
    sheet_name: RequiredText = FORM_SOURCE_DEFAULT_SHEET
    ignored_headers: list[str] = Field(default_factory=lambda: ["Timestamp"])
    poll_interval_seconds: Annotated[
        int,
        Field(ge=1, le=FORM_SOURCE_MAX_INTERVAL),
    ] = FORM_SOURCE_DEFAULT_INTERVAL
    enabled: bool = True

    @field_validator("spreadsheet_id")
    @classmethod
    def validate_spreadsheet_id(cls, value: str) -> str:
        return normalize_spreadsheet_id(value)

    @field_validator("ignored_headers")
    @classmethod
    def validate_ignored_headers(cls, value: list[str]) -> list[str]:
        return normalize_ignored_headers(value)


class FormSourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spreadsheet_id: RequiredText | None = None
    sheet_name: RequiredText | None = None
    ignored_headers: list[str] | None = None
    poll_interval_seconds: Annotated[
        int,
        Field(ge=1, le=FORM_SOURCE_MAX_INTERVAL),
    ] | None = None

    @field_validator("spreadsheet_id")
    @classmethod
    def validate_spreadsheet_id(cls, value: str | None) -> str | None:
        return normalize_spreadsheet_id(value) if value is not None else None

    @field_validator("ignored_headers")
    @classmethod
    def validate_ignored_headers(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        return normalize_ignored_headers(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "FormSourceUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one editable field is required")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("editable fields cannot be null")
        return self


class FormSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    form_id: str
    spreadsheet_id: str
    sheet_name: str
    ignored_headers: list[str]
    enabled: bool
    last_read_row: int
    poll_interval_seconds: int
    next_poll_at: datetime
    last_polled_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class FormSourcePageResponse(BaseModel):
    items: list[FormSourceResponse] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


def form_source_response(row: Any) -> FormSourceResponse:
    return FormSourceResponse.model_validate(dict(row))
