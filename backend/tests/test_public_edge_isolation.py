"""Static isolation checks for the public nginx edge before public routes exist."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import unittest


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
if not COMPOSE.exists():
    COMPOSE = Path("/compose.yaml")
FRONTEND = ROOT / "frontend"
if not FRONTEND.exists():
    FRONTEND = Path("/workspace/frontend")


class PublicEdgeIsolationTests(unittest.TestCase):
    def test_default_public_service_and_admin_profile_are_separate(self) -> None:
        compose = COMPOSE.read_text()
        public = compose[compose.index("  public-web:"):compose.index("  google-sheets:")]
        admin = compose[compose.index("  admin-web:"):compose.index("  public-web:")]
        self.assertIn("context: ./frontend/public", public)
        self.assertIn('"${PUBLIC_PORT:-8080}:8080"', public)
        self.assertNotIn("profiles:", public)
        self.assertIn('profiles: ["admin"]', admin)
        self.assertIn('127.0.0.1:${ADMIN_PORT:-8081}:8080', admin)

    def test_public_nginx_rewrites_only_declared_routes(self) -> None:
        nginx = (FRONTEND / "public/nginx/default.conf").read_text()
        self.assertNotIn("try_files $uri $uri/ /index.html", nginx)
        self.assertIn("location = /healthz", nginx)
        self.assertIn("location /assets/", nginx)
        for route in ("/", "/insights", "/themes", "/about", "/robots.txt", "/sitemap.xml"):
            self.assertIn(f"location = {route}", nginx)
        self.assertIn("location @public_not_found", nginx)
        self.assertIn("internal;", nginx)

    def test_public_assets_are_self_contained_and_responsive(self) -> None:
        css = (FRONTEND / "public/assets/site.css").read_text()
        public_files = "\n".join(path.read_text() for path in (FRONTEND / "public/assets").rglob("*") if path.is_file())
        self.assertNotIn("frontend/admin", public_files)
        self.assertNotIn("http://", public_files)
        self.assertNotIn("https://", public_files)
        self.assertNotIn("fetch(", public_files)
        self.assertIn("@media(max-width:40rem)", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("focus-visible", css)
        for token in ("--forest", "--mint", ".card-grid", ".theme-pill", ".search-form", ".empty-state", ".article-content"):
            self.assertIn(token, css)

    @unittest.skipUnless(
        os.environ.get("PUBLIC_EDGE_BASE_URL"),
        "PUBLIC_EDGE_BASE_URL is provided by compose.test.yaml",
    )
    def test_public_edge_container_serves_only_local_public_resources(self) -> None:
        """Exercise the built nginx image across the Compose network.

        This is intentionally an HTTP-level check: a harmless-looking nginx
        configuration change must not turn the public service into a proxy for
        internal routes.
        """
        base_url = os.environ["PUBLIC_EDGE_BASE_URL"].rstrip("/")

        for path in ("/healthz", "/favicon.svg", "/assets/site.css", "/", "/insights", "/themes", "/about", "/robots.txt", "/sitemap.xml"):
            with self.subTest(allowed_path=path):
                with urlopen(f"{base_url}{path}", timeout=5) as response:
                    self.assertEqual(response.status, 200)

        request = Request(f"{base_url}/", headers={"Host": "attacker.example"})
        with urlopen(request, timeout=5) as response:
            page = response.read().decode()
            self.assertIn('https://library.example.test/', page)
            self.assertNotIn("attacker.example", page)
            self.assertEqual(response.headers["Cache-Control"], "public, max-age=300")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["Referrer-Policy"], "strict-origin-when-cross-origin")
            self.assertEqual(response.headers["Permissions-Policy"], "camera=(), geolocation=(), microphone=()")
            self.assertIn("script-src 'none'", response.headers["Content-Security-Policy"])
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

        with urlopen(f"{base_url}/robots.txt", timeout=5) as response:
            robots = response.read().decode()
            for path in ("/_site/", "/api/", "/admin", "/dashboard", "/operations", "/articles", "/inputs", "/taxonomy"):
                self.assertIn(f"Disallow: {path}", robots)
        with urlopen(f"{base_url}/sitemap.xml", timeout=5) as response:
            sitemap = ElementTree.fromstring(response.read())
        for node in sitemap.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url"):
            location = node.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            self.assertIsNotNone(location)
            path = urlparse(location).path
            with self.subTest(sitemap_path=path), urlopen(f"{base_url}{path}", timeout=5) as response:
                self.assertEqual(response.status, 200)

        forbidden_paths = (
            "/unknown-public-path",
            "/api/healthz",
            "/_site/",
            "/articles",
            "/articles/1",
            "/inputs",
            "/operations/summary",
            "/form-sources",
            "/generation",
            "/article-generation-jobs",
            "/article-generation-jobs/1",
            "/taxonomy",
            "/taxonomy-runs",
        )
        for path in forbidden_paths:
            with self.subTest(forbidden_path=path):
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"{base_url}{path}", timeout=5)
                self.assertEqual(error.exception.code, 404)
                self.assertNotIn("api", error.exception.read().decode().lower())
