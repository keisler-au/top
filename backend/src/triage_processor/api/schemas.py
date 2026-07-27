from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
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


class InputCreate(BaseModel):
    original_text: RequiredText
    source: RequiredText
    submission_key: RequiredText | None = None
    question_context: QuestionContext | None = None

    @model_validator(mode="after")
    def require_question_context_for_submission(self) -> "InputCreate":
        if self.submission_key is not None and self.question_context is None:
            raise ValueError(
                "submission_key is only allowed when question_context is present"
            )
        return self


class ThemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None


class InputResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_text: str
    source: str
    status: str
    topic: str | None
    question_id: int | None
    question_context: QuestionContext | None
    submission_key: str | None
    created_at: datetime
    themes: list[ThemeResponse] = Field(default_factory=list)
