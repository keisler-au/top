from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PublicTheme:
    id: int
    name: str
    slug: str


@dataclass(frozen=True)
class PublicArticle:
    slug: str
    title: str
    excerpt: str
    html: str
    published_at: datetime
    updated_at: datetime
    reading_minutes: int
    themes: tuple[PublicTheme, ...]
