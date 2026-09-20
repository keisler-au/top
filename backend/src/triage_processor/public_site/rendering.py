"""Small escaped HTML renderer; content HTML is sanitized at the boundary."""
import html
import json
from urllib.parse import quote

from triage_processor.public_site.schemas import PublicArticle, PublicTheme
from triage_processor.public_site.settings import PublicSiteSettings

SETTINGS = PublicSiteSettings.from_env()

def esc(value: object) -> str: return html.escape(str(value), quote=True)
def url(path: str) -> str: return SETTINGS.origin + quote(path, safe="/%?=&-")
def layout(title: str, body: str, path: str, description: str = "", *, article: PublicArticle | None = None) -> str:
    canonical = url(path)
    summary = description or SETTINGS.description or SETTINGS.name
    open_graph = f'<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(summary)}"><meta property="og:url" content="{esc(canonical)}"><meta property="og:site_name" content="{esc(SETTINGS.name)}"><meta property="og:type" content="{"article" if article else "website"}">'
    json_ld = ""
    if article:
        payload = {
            "@context": "https://schema.org", "@type": "Article", "headline": article.title,
            "description": article.excerpt, "mainEntityOfPage": canonical,
            "datePublished": article.published_at.isoformat(), "dateModified": article.updated_at.isoformat(),
        }
        json_ld = '<script type="application/ld+json">' + json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c") + "</script>"
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} | {esc(SETTINGS.name)}</title><meta name="description" content="{esc(summary)}"><link rel="canonical" href="{esc(canonical)}">{open_graph}{json_ld}<link rel="stylesheet" href="/assets/site.css"></head><body><a class="skip-link" href="#main">Skip to content</a><header class="site-header"><div class="shell header-row"><a class="site-name" href="/">{esc(SETTINGS.name)}</a><nav aria-label="Primary"><a href="/insights">Insights</a><a href="/themes">Themes</a><a href="/about">About</a></nav></div></header><main id="main" class="shell">{body}</main><footer class="site-footer"><div class="shell"><p>{esc(SETTINGS.name)} · A read-only editorial library.</p></div></footer></body></html>'
def theme_link(theme: PublicTheme) -> str: return f'<a class="theme-pill" href="/themes/{theme.id}-{quote(theme.slug)}">{esc(theme.name)}</a>'
def card(article: PublicArticle) -> str: return f'<article class="insight-card"><h2><a href="/insights/{quote(article.slug)}">{esc(article.title)}</a></h2><p>{esc(article.excerpt)}</p><p class="meta">{article.reading_minutes} min read</p></article>'
def article_page(article: PublicArticle, related: list[PublicArticle]) -> str:
    tags = " ".join(theme_link(theme) for theme in article.themes)
    related_html = "".join(card(item) for item in related) or "<p>No related insights yet.</p>"
    return layout(article.title, f'<article class="article-layout"><header class="article-header"><p class="eyebrow">Insight</p><h1>{esc(article.title)}</h1><p class="meta">{esc(article.published_at.date())} · {article.reading_minutes} min read</p><p class="theme-list">{tags}</p></header><div class="article-content">{article.html}</div></article><aside class="related" aria-label="Related insights"><h2>Related insights</h2><div class="card-grid">{related_html}</div></aside>', f'/insights/{article.slug}', article.excerpt, article=article)
