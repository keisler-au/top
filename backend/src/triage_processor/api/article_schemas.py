from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

ArticleStatus = Literal["draft", "ready_for_review", "approved", "archived"]
ArticleAction = Literal[
    "created",
    "revised",
    "submitted",
    "approved",
    "returned_to_draft",
    "archived",
]
NonemptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ArticleTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[NonemptyText, StringConstraints(max_length=120)]


class ArticleEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: NonemptyText
    citation_id: Annotated[str, StringConstraints(max_length=200)] | None = None


class ArticleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[NonemptyText, StringConstraints(max_length=500)]
    structured_content: dict[str, Any]
    rendered_html: str | None = None
    generation_metadata: dict[str, Any] | None = None
    theme_ids: list[int] = Field(default_factory=list)
    topics: list[ArticleTopic] = Field(default_factory=list)
    evidence: list[ArticleEvidenceInput] = Field(min_length=1)


class ArticlePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[NonemptyText, StringConstraints(max_length=500)] | None = None
    structured_content: dict[str, Any] | None = None
    rendered_html: str | None = None
    generation_metadata: dict[str, Any] | None = None
    theme_ids: list[int] | None = None
    topics: list[ArticleTopic] | None = None
    evidence: list[ArticleEvidenceInput] | None = None
    expected_revision_id: int | None = Field(default=None, ge=1)


class ArticlePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[NonemptyText, StringConstraints(max_length=500)]
    structured_content: dict[str, Any]
    expected_revision_id: int | None = Field(default=None, ge=1)


class ArticlePreviewResponse(BaseModel):
    rendered_html: str


class ArticleTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Annotated[str, StringConstraints(max_length=2000)] | None = None
    actor: Annotated[str, StringConstraints(max_length=200)] | None = None


class ArticleRevisionResponse(BaseModel):
    id: int
    revision_number: int
    title: str
    structured_content: dict[str, Any]
    rendered_html: str | None
    template_version_id: int | None
    created_at: datetime


class ArticleResponse(BaseModel):
    id: int
    title: str
    status: ArticleStatus
    current_revision: ArticleRevisionResponse
    generation_metadata: dict[str, Any] | None
    theme_ids: list[int]
    topics: list[ArticleTopic]
    evidence_count: int
    approved_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ArticleListResponse(BaseModel):
    items: list[ArticleResponse]
    total: int
    page: int
    page_size: int


class ArticleEvidenceResponse(BaseModel):
    id: int
    evidence_id: str
    evidence_order: int
    citation_id: str | None
    topic_key: str
    text: str
    original_input_id: int
    evidence_type: Literal["original", "segment"]
    original_text: str
    topic_name: str
    source: str
    submission_key: str | None
    question_context: dict[str, Any] | None


class ArticleAuditResponse(BaseModel):
    id: int
    revision_id: int | None
    action: ArticleAction
    actor: str | None
    note: str | None
    created_at: datetime
