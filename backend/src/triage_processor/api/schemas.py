from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

RequiredText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class InputCreate(BaseModel):
    original_text: RequiredText
    source: RequiredText


class InputResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_text: str
    source: str
    status: str
    topic: str | None
    created_at: datetime
