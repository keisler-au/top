import html
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import nh3

PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-z_]+)\s*}}")
SUPPORTED_PLACEHOLDERS = {"title", "standfirst", "article_body", "published_at"}
REQUIRED_PLACEHOLDERS = {"title", "article_body"}
BLOCKED_TAGS = {
    "base",
    "button",
    "embed",
    "form",
    "iframe",
    "input",
    "link",
    "meta",
    "object",
    "script",
    "select",
    "style",
    "svg",
    "textarea",
}
ALLOWED_TAGS = {
    "a",
    "article",
    "blockquote",
    "br",
    "em",
    "h1",
    "h2",
    "h3",
    "header",
    "hr",
    "li",
    "main",
    "ol",
    "p",
    "section",
    "strong",
    "time",
    "ul",
}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}, "time": {"datetime"}}
VOID_TAGS = {"br", "hr"}


class _TemplateSafetyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in BLOCKED_TAGS:
            self.errors.append(f"unsafe element <{tag}> is not allowed")
        if normalized_tag not in ALLOWED_TAGS:
            self.errors.append(f"element <{tag}> is not allowed")
        elif normalized_tag not in VOID_TAGS:
            self.open_tags.append(normalized_tag)
        for name, value in attrs:
            normalized_name = name.casefold()
            if normalized_name.startswith("on") or normalized_name == "style":
                self.errors.append(f"unsafe attribute {name!r} is not allowed")
            if normalized_name == "src":
                self.errors.append("remote and embedded assets are not allowed")
            if normalized_name == "href" and value:
                parsed = urlparse(value.strip())
                if parsed.scheme and parsed.scheme.casefold() not in {"http", "https", "mailto"}:
                    self.errors.append("unsafe link scheme is not allowed")

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        normalized_tag = tag.casefold()
        if normalized_tag not in VOID_TAGS and self.open_tags:
            self.open_tags.pop()

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in VOID_TAGS:
            return
        if not self.open_tags or self.open_tags[-1] != normalized_tag:
            self.errors.append(f"mismatched closing element </{tag}>")
            return
        self.open_tags.pop()


def validate_template_source(source: str) -> list[str]:
    if not source.strip():
        raise ValueError("template HTML cannot be blank")
    placeholders = PLACEHOLDER_PATTERN.findall(source)
    unknown = sorted(set(placeholders) - SUPPORTED_PLACEHOLDERS)
    if unknown:
        raise ValueError(f"unsupported template placeholders: {unknown}")
    for required in sorted(REQUIRED_PLACEHOLDERS):
        if placeholders.count(required) != 1:
            raise ValueError(f"template must contain {{{{{required}}}}} exactly once")

    parser = _TemplateSafetyParser()
    parser.feed(source)
    parser.close()
    if parser.open_tags:
        parser.errors.append(
            "unclosed elements: " + ", ".join(f"<{tag}>" for tag in parser.open_tags)
        )
    if parser.errors:
        raise ValueError("; ".join(dict.fromkeys(parser.errors)))

    sanitized = sanitize_html(source)
    if not sanitized.strip():
        raise ValueError("template contains no safe HTML")
    return list(dict.fromkeys(placeholders))


def sanitize_html(value: str) -> str:
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        clean_content_tags=BLOCKED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        strip_comments=True,
        link_rel="noopener noreferrer",
    )


def _article_body(sections: list[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for section in sections:
        heading = html.escape(str(section["heading"]))
        rendered.append(f"<section><h2>{heading}</h2>")
        for paragraph in section["paragraphs"]:
            rendered.append(f"<p>{html.escape(str(paragraph))}</p>")
        rendered.append("</section>")
    return "".join(rendered)


def render_template(source: str, content: dict[str, Any]) -> str:
    validate_template_source(source)
    replacements = {
        "title": html.escape(str(content.get("title", ""))),
        "standfirst": html.escape(str(content.get("standfirst", ""))),
        "article_body": _article_body(list(content.get("sections", []))),
        "published_at": html.escape(datetime.now(UTC).isoformat()),
    }
    rendered = PLACEHOLDER_PATTERN.sub(
        lambda match: replacements[match.group(1)],
        source,
    )
    return sanitize_html(rendered)
