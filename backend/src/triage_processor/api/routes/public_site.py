"""Internal-only HTML renderer. The public nginx edge does not expose it yet."""
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from triage_processor.public_site import rendering, service

router = APIRouter(prefix="/_site", include_in_schema=False)


def not_found() -> HTMLResponse:
    return HTMLResponse(rendering.layout("Page not found", "<h1>Page not found</h1><p>The page you requested is unavailable.</p>", "/404"), status_code=404)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    async with request.app.state.db_pool.acquire() as connection:
        articles = await service.all_articles(connection)
        public_themes = await service.themes(connection)
    cards = "".join(rendering.card(article) for article in articles[:3]) or '<p class="empty-state">No published insights yet.</p>'
    themes = " ".join(rendering.theme_link(theme) for theme in public_themes[:8]) or '<p class="empty-state">No themes yet.</p>'
    return HTMLResponse(rendering.layout("Home", f'<section class="hero"><p class="eyebrow">Evidence-led insights</p><h1>Ideas shaped by what people share.</h1><p>We collect responses, identify recurring themes, and publish careful editorial insights.</p><a class="button" href="/insights">Browse insights</a></section><section class="section"><div class="section-heading"><h2>Latest insights</h2><a href="/insights">View all</a></div><div class="card-grid">{cards}</div></section><section class="section split"><div><h2>How this library works</h2><ol><li>Collect responses</li><li>Identify recurring themes</li><li>Publish editorial insights</li></ol></div><div><h2>Explore themes</h2><p class="theme-list">{themes}</p><a href="/about">About this library</a></div></section>', "/"))


@router.get("/insights", response_class=HTMLResponse)
async def insights(request: Request, q: str | None = None, page: int = 1) -> HTMLResponse:
    if set(request.query_params) - {"q", "page"}:
        return not_found()
    try:
        async with request.app.state.db_pool.acquire() as connection:
            articles, total = await service.list_articles(connection, search=q, page=page)
    except ValueError:
        return not_found()
    cards = "".join(rendering.card(article) for article in articles) or "<p>No published insights match your search.</p>"
    search = rendering.esc(q.strip()) if q else ""
    pager = f"<p>Showing {len(articles)} of {total} insights.</p>"
    return HTMLResponse(rendering.layout("Insights", f'<section class="page-heading"><p class="eyebrow">Library</p><h1>Insights</h1><p>Browse published editorial insights.</p></section><form class="search-form" method="get" action="/insights"><label for="search">Search insights</label><input id="search" name="q" value="{search}"><button type="submit">Search</button></form><p class="meta">{pager}</p><div class="card-grid">{cards}</div>', "/insights"))


@router.get("/insights/{slug}", response_class=HTMLResponse)
async def insight_detail(slug: str, request: Request) -> HTMLResponse:
    async with request.app.state.db_pool.acquire() as connection:
        article = await service.article_by_slug(connection, slug)
        if article is None: return not_found()
        related = await service.related(connection, article)
    return HTMLResponse(rendering.article_page(article, related))


@router.get("/themes", response_class=HTMLResponse)
async def theme_directory(request: Request) -> HTMLResponse:
    async with request.app.state.db_pool.acquire() as connection: public_themes = await service.themes(connection)
    body = "".join(f"<li>{rendering.theme_link(theme)}</li>" for theme in public_themes) or "<p>No public themes yet.</p>"
    return HTMLResponse(rendering.layout("Themes", f"<h1>Themes</h1><ul>{body}</ul>", "/themes"))


@router.get("/themes/{theme_id}-{slug}", response_class=HTMLResponse)
async def theme_detail(theme_id: int, slug: str, request: Request) -> HTMLResponse:
    async with request.app.state.db_pool.acquire() as connection:
        theme = await service.resolve_theme(connection, theme_id)
        if theme is None: return not_found()
        articles = await service.articles_for_theme(connection, theme.id)
    cards = "".join(rendering.card(article) for article in articles) or "<p>No published insights for this theme.</p>"
    return HTMLResponse(rendering.layout(theme.name, f"<h1>{rendering.esc(theme.name)}</h1>{cards}", f"/themes/{theme.id}-{theme.slug}"))


@router.get("/about", response_class=HTMLResponse)
async def about() -> HTMLResponse:
    return HTMLResponse(rendering.layout("About", "<h1>About</h1><p>This library publishes evidence-led insights.</p>", "/about"))


@router.get("/robots.txt")
async def robots() -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /_site/\nDisallow: /api/\nDisallow: /admin\nDisallow: /dashboard\nDisallow: /operations\nDisallow: /articles\nDisallow: /inputs\nDisallow: /taxonomy\n")


@router.get("/sitemap.xml")
async def sitemap(request: Request) -> Response:
    async with request.app.state.db_pool.acquire() as connection:
        articles = await service.all_articles(connection)
        public_themes = await service.themes(connection)
    paths = ["/", "/insights", "/themes", "/about"] + [f"/insights/{article.slug}" for article in articles] + [f"/themes/{theme.id}-{theme.slug}" for theme in public_themes]
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{xml_escape(rendering.url(path))}</loc></url>" for path in paths) + "</urlset>"
    return Response(xml, media_type="application/xml")


@router.get("/{path:path}", response_class=HTMLResponse)
async def site_fallback(path: str) -> HTMLResponse:
    return not_found()
