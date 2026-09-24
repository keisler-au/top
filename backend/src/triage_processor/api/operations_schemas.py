from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QueueStageMetrics(BaseModel):
    stage: str
    pending: int = 0
    processing: int = 0
    retrying: int = 0
    failed: int = 0
    oldest_ready_wait_seconds: int | None = None


class TaxonomyRunMetrics(BaseModel):
    active: int = 0
    review_backlog: int = 0
    snapshot_evidence_count: int = 0
    noise_count: int = 0
    validation_failures: int = 0
    last_published_at: datetime | None = None
    automation_state: Literal["preparing_evidence", "waiting_for_automation", "running_candidate", "automatically_published", "blocked_by_quality", "blocked_by_failure", "blocked_by_policy", "scheduler_unavailable"] = "preparing_evidence"
    automation_policy_version: str | None = None
    automation_failure_code: str | None = None


class OperationsSummaryResponse(BaseModel):
    evidence_pipeline: list[QueueStageMetrics] = Field(default_factory=list)
    topic_validation_corrections: int = 0
    topic_terminal_failures: int = 0
    last_theme_refresh_at: datetime | None = None
    pending_theme_materializations: int = 0
    article_generation: QueueStageMetrics
    average_generation_duration_seconds: int | None = None
    enabled_form_sources: int = 0
    form_poll_failures: int = 0
    oldest_form_cursor_age_seconds: int | None = None
    approvals_last_24_hours: int = 0
    taxonomy_runs: TaxonomyRunMetrics = Field(default_factory=TaxonomyRunMetrics)
