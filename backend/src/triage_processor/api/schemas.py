from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

RequiredText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class QuestionContext(BaseModel):
    form_key: RequiredText
    question_key: RequiredText
    question_version: Annotated[int, Field(ge=1)] = 1
    question_text: RequiredText
    form_id: RequiredText | None = None


class InputCreate(BaseModel):
    original_text: RequiredText
    source: RequiredText
    submission_key: RequiredText | None = None
    source_record_key: RequiredText | None = None
    question_context: QuestionContext


class ThemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None


class TopicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class InputResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_text: str
    source: str
    status: str
    question_id: int
    question_context: QuestionContext
    submission_key: str | None
    source_record_key: str | None
    created_at: datetime
    topics: list[TopicResponse] = Field(default_factory=list)
    themes: list[ThemeResponse] = Field(default_factory=list)
    published_taxonomy_run_id: int | None = None
