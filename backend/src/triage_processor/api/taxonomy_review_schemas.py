from datetime import datetime

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaxonomyRunCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=200)
    configuration: dict[str, Any]
    embedding_model: str = Field(min_length=1, max_length=200)
    embedding_representation: str = Field(min_length=1, max_length=200)
    embedding_dimension: int = Field(gt=0, le=100_000)
    clustering_model: str = Field(min_length=1, max_length=200)
    topic_model: str = Field(min_length=1, max_length=200)
    theme_model: str = Field(min_length=1, max_length=200)
    topic_prompt_version: str = Field(min_length=1, max_length=200)
    theme_prompt_version: str = Field(min_length=1, max_length=200)

    @field_validator("configuration")
    @classmethod
    def require_versioned_clustering_configuration(
        cls, value: dict[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(value.get("version"), str) or not value["version"].strip():
            raise ValueError("configuration.version must be a non-blank string")
        if not isinstance(value.get("clustering"), dict):
            raise ValueError("configuration.clustering must be an object")
        return value


class TaxonomyRunCreated(BaseModel):
    id: int
    status: str
    source_cutoff: datetime
    evidence_count: int
    embedding_dimension: int
    queued: bool
    reused: bool


class TaxonomyRunDecision(BaseModel):
    expected_updated_at: datetime
    operator: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class TaxonomyRunSummary(BaseModel):
    id: int
    status: str
    source_cutoff: datetime
    updated_at: datetime
    topic_count: int
    noise_count: int
    theme_count: int
    validation_failure_count: int
    changed_membership_count: int


class TaxonomyTopicAntecedent(BaseModel):
    id: int
    name: str
    description: str
    question_id: int | None
    support_count: int
    relationship: str
    reconciliation_decision_id: int


class TaxonomyRunTopicReview(BaseModel):
    id: int
    topic_id: int
    name: str
    description: str
    support_count: int
    continuity_decision: str
    representative_evidence_ids: list[int] = Field(default_factory=list)
    antecedent_provisional_topic_ids: list[int] = Field(default_factory=list)
    antecedents: list[TaxonomyTopicAntecedent] = Field(default_factory=list)


class TaxonomyClusterReview(BaseModel):
    id: int
    question_id: int | None
    support_count: int
    outcome: str
    reasons: list[str] = Field(default_factory=list)
    provisional_topic_id: int | None = None
    provisional_name: str | None = None


class TaxonomyRunReview(TaxonomyRunSummary):
    topics: list[TaxonomyRunTopicReview] = Field(default_factory=list)
    candidate_theme_count: int
    evidence_count: int = 0
    evidence_with_topic_count: int = 0
    evidence_without_topic_count: int = 0
    clusters: list[TaxonomyClusterReview] = Field(default_factory=list)
    gate_passed: bool | None = None
    publication_failures: list[str] = Field(default_factory=list)
    threshold_version: str | None = None
    truncated: bool = False


