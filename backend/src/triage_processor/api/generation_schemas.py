from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

NonemptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[NonemptyText, StringConstraints(max_length=120)]
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None
    html_source: NonemptyText
    created_by: Annotated[str, StringConstraints(max_length=200)] | None = None


class TemplateVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    html_source: NonemptyText
    created_by: Annotated[str, StringConstraints(max_length=200)] | None = None


class TemplatePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: int = Field(ge=1)
    title: str = "Example article"
    standfirst: str = "An example introduction."
    sections: list[dict[str, object]] = Field(
        default_factory=lambda: [
            {"heading": "Example section", "paragraphs": ["Example content."]}
        ]
    )


class TemplateVersionResponse(BaseModel):
    id: int
    version: int
    allowed_placeholders: list[str]
    created_by: str | None
    created_at: datetime


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: str | None
    status: Literal["active", "archived"]
    versions: list[TemplateVersionResponse]
    created_at: datetime
    updated_at: datetime


class TemplatePreviewResponse(BaseModel):
    rendered_html: str


class GenerationJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: Literal["specific", "most-evidence", "least-covered"] = "specific"
    taxonomy_type: Literal["theme", "topic"]
    taxonomy_key: NonemptyText
    template_version_id: int = Field(ge=1)
    editorial_guidance: Annotated[str, StringConstraints(max_length=4000)] | None = None
    evidence_ids: list[NonemptyText] | None = Field(default=None, max_length=100)


class GenerationJobResponse(BaseModel):
    id: int
    status: Literal["pending", "processing", "completed", "failed", "dismissed"]
    strategy: str
    taxonomy_type: str
    taxonomy_key: str
    taxonomy_name: str
    template_version_id: int
    editorial_guidance: str | None
    attempts: int
    available_at: datetime
    last_error: str | None
    resulting_article_id: int | None
    status_url: str
    created_at: datetime
    updated_at: datetime


class GeneratedSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: Annotated[NonemptyText, StringConstraints(max_length=300)]
    paragraphs: list[Annotated[NonemptyText, StringConstraints(max_length=4000)]] = Field(
        min_length=1,
        max_length=20,
    )
    evidence_ids: list[NonemptyText] = Field(min_length=1, max_length=100)


class GeneratedArticle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[NonemptyText, StringConstraints(max_length=500)]
    standfirst: Annotated[str, StringConstraints(max_length=1000)] = ""
    sections: list[GeneratedSection] = Field(min_length=1, max_length=30)
    theme_ids: list[int] = Field(default_factory=list, max_length=20)
    topic_keys: list[NonemptyText] = Field(default_factory=list, max_length=50)
