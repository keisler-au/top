from datetime import datetime

from pydantic import BaseModel, Field


class QueueStageMetrics(BaseModel):
    stage: str
    pending: int = 0
    processing: int = 0
    retrying: int = 0
    failed: int = 0
    oldest_ready_wait_seconds: int | None = None


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
