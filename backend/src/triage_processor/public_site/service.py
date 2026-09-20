"""Parameterized queries over the public projection only."""
import html
import re
from math import ceil

import asyncpg

from triage_processor.public_site.schemas import PublicArticle, PublicTheme
from triage_processor.templates import sanitize_html

PAGE_DEFAULT = 12
PAGE_MAX = 48
OFFSET_MAX = 10_000
_TAG_RE = re.compile(r"<[^>]+>")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-") or "theme"


def excerpt(value: str, limit: int = 220) -> str:
    text = " ".join(html.unescape(_TAG_RE.sub(" ", value)).split())
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def reading_minutes(value: str) -> int:
    return max(1, ceil(len(_TAG_RE.sub(" ", value).split()) / 200))


async def _themes(connection: asyncpg.Connection, article_id: int, revision_id: int) -> tuple[PublicTheme, ...]:
    rows = await connection.fetch("""
        SELECT snapshots.stable_theme_id, snapshots.display_name
        FROM article_publication_themes AS snapshots
        WHERE snapshots.article_id=$1 AND snapshots.approved_revision_id=$2
        ORDER BY lower(snapshots.display_name), snapshots.stable_theme_id
    """, article_id, revision_id)
    return tuple(PublicTheme(int(row["stable_theme_id"]), row["display_name"], slugify(row["display_name"])) for row in rows)


async def _article(connection: asyncpg.Connection, row: asyncpg.Record) -> PublicArticle:
    safe_html = sanitize_html(row["rendered_html"] or "")
    # The page shell owns the sole h1; generated article fragments may have
    # one from the editorial preview, so demote it at the public boundary.
    safe_html = re.sub(r"</?h1\b[^>]*>", lambda match: "</h2>" if match.group(0).startswith("</") else "<h2>", safe_html, flags=re.I)
    return PublicArticle(
        slug=row["slug"], title=row["title"], excerpt=excerpt(safe_html), html=safe_html,
        published_at=row["first_published_at"], updated_at=row["updated_at"],
        reading_minutes=reading_minutes(safe_html),
        themes=await _themes(connection, row["article_id"], row["approved_revision_id"]),
    )


_ACTIVE = """
    FROM article_publications AS publications
    JOIN articles ON articles.id=publications.article_id AND articles.status='approved'
    JOIN article_revisions AS revisions
      ON revisions.id=publications.approved_revision_id
     AND articles.current_revision_id=publications.approved_revision_id
"""
_SELECT = """SELECT publications.article_id, publications.approved_revision_id,
    publications.slug, publications.first_published_at, publications.updated_at,
    revisions.title, revisions.rendered_html """


async def list_articles(connection: asyncpg.Connection, *, search: str | None, page: int) -> tuple[list[PublicArticle], int]:
    if page < 1 or (page - 1) * PAGE_DEFAULT > OFFSET_MAX:
        raise ValueError("page is outside the public library range")
    term = search.strip() if search else None
    if term == "": term = None
    if term and len(term) > 120: raise ValueError("search is too long")
    predicate = "($1::text IS NULL OR revisions.title ILIKE '%' || $1 || '%')"
    total = await connection.fetchval("SELECT count(*) " + _ACTIVE + " WHERE " + predicate, term)
    rows = await connection.fetch(_SELECT + _ACTIVE + " WHERE " + predicate + " ORDER BY publications.updated_at DESC, publications.article_id DESC OFFSET $2 LIMIT $3", term, (page - 1) * PAGE_DEFAULT, PAGE_DEFAULT)
    return [await _article(connection, row) for row in rows], int(total)


async def article_by_slug(connection: asyncpg.Connection, slug: str) -> PublicArticle | None:
    row = await connection.fetchrow(_SELECT + _ACTIVE + " WHERE publications.slug=$1", slug)
    return await _article(connection, row) if row else None


async def all_articles(connection: asyncpg.Connection) -> list[PublicArticle]:
    rows = await connection.fetch(_SELECT + _ACTIVE + " ORDER BY publications.updated_at DESC, publications.article_id DESC")
    return [await _article(connection, row) for row in rows]


async def themes(connection: asyncpg.Connection) -> list[PublicTheme]:
    rows = await connection.fetch("""
        SELECT DISTINCT snapshots.stable_theme_id, snapshots.display_name,
               lower(snapshots.display_name) AS sort_name
        FROM article_publication_themes AS snapshots
        JOIN article_publications AS publications
          ON publications.article_id=snapshots.article_id
         AND publications.approved_revision_id=snapshots.approved_revision_id
        JOIN articles ON articles.id=publications.article_id AND articles.status='approved'
        ORDER BY sort_name, snapshots.stable_theme_id
    """)
    return [PublicTheme(int(row["stable_theme_id"]), row["display_name"], slugify(row["display_name"])) for row in rows]


async def resolve_theme(connection: asyncpg.Connection, requested_id: int) -> PublicTheme | None:
    resolved = await connection.fetchval("SELECT theme_id FROM resolve_published_theme_id($1) WHERE resolution='resolved'", requested_id)
    theme_id = int(resolved) if resolved is not None else requested_id
    row = await connection.fetchrow("""
        SELECT snapshots.stable_theme_id, snapshots.display_name
        FROM article_publication_themes AS snapshots
        JOIN article_publications AS publications ON publications.article_id=snapshots.article_id AND publications.approved_revision_id=snapshots.approved_revision_id
        JOIN articles ON articles.id=publications.article_id AND articles.status='approved'
        WHERE snapshots.stable_theme_id=$1
        ORDER BY publications.updated_at DESC LIMIT 1
    """, theme_id)
    return PublicTheme(int(row["stable_theme_id"]), row["display_name"], slugify(row["display_name"])) if row else None


async def articles_for_theme(connection: asyncpg.Connection, theme_id: int) -> list[PublicArticle]:
    rows = await connection.fetch(_SELECT + _ACTIVE + " JOIN article_publication_themes snapshots ON snapshots.article_id=publications.article_id AND snapshots.approved_revision_id=publications.approved_revision_id WHERE snapshots.stable_theme_id=$1 ORDER BY publications.updated_at DESC, publications.article_id DESC", theme_id)
    return [await _article(connection, row) for row in rows]


async def related(connection: asyncpg.Connection, article: PublicArticle) -> list[PublicArticle]:
    ids = [theme.id for theme in article.themes]
    if not ids: return []
    rows = await connection.fetch(_SELECT + _ACTIVE + " JOIN article_publication_themes snapshots ON snapshots.article_id=publications.article_id AND snapshots.approved_revision_id=publications.approved_revision_id WHERE publications.slug <> $1 AND snapshots.stable_theme_id=ANY($2::bigint[]) GROUP BY publications.article_id, publications.approved_revision_id, publications.slug, publications.first_published_at, publications.updated_at, revisions.title, revisions.rendered_html ORDER BY count(DISTINCT snapshots.stable_theme_id) DESC, publications.updated_at DESC LIMIT 3", article.slug, ids)
    return [await _article(connection, row) for row in rows]
