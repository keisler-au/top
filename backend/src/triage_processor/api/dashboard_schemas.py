from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TaxonomyType = Literal["theme", "topic"]
CoverageState = Literal["no_evidence", "uncovered", "covered"]
EvidenceType = Literal["original", "segment"]
RecommendationStrategy = Literal["most-evidence", "least-covered"]


class DashboardSummaryResponse(BaseModel):
    evidence_count: int = 0
    theme_count: int = 0
    topic_count: int = 0
    article_count: int = 0
    awaiting_approval_count: int = 0
    failed_generation_count: int = 0


class TaxonomyItemResponse(BaseModel):
    type: TaxonomyType
    key: int | str
    name: str
    description: str | None = None
    evidence_count: int = 0
    article_count: int = 0
    approved_article_count: int = 0
    coverage_state: CoverageState
    generation_eligible: bool


class TaxonomyPageResponse(BaseModel):
    items: list[TaxonomyItemResponse] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class EvidenceQuestionContextResponse(BaseModel):
    form_key: str
    form_id: str | None = None
    question_key: str
    question_version: int
    question_text: str


class EvidenceItemResponse(BaseModel):
    id: str
    type: EvidenceType
    excerpt: str
    original_text: str
    original_input_id: int
    segment_order: int | None = None
    topic_key: str
    topic_name: str
    source: str
    submission_key: str | None = None
    source_record_key: str | None = None
    question_context: EvidenceQuestionContextResponse | None = None
    created_at: datetime


class EvidencePageResponse(BaseModel):
    items: list[EvidenceItemResponse] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class RecommendationItemResponse(TaxonomyItemResponse):
    explanation: str


class RecommendationResponse(BaseModel):
    taxonomy_type: TaxonomyType
    strategy: RecommendationStrategy
    items: list[RecommendationItemResponse] = Field(default_factory=list)

