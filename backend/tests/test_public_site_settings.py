"""PW-WP5 deployment, discovery, and edge-header contracts."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from triage_processor.public_site.settings import PublicSiteSettings


class PublicSiteSettingsTests(TestCase):
    def test_origin_rejects_paths_credentials_and_non_http_schemes(self) -> None:
        for origin in ("example.test", "ftp://example.test", "https://example.test/path", "https://user:pass@example.test", "https://example.test/?q=x", "https://example.test/#x"):
            with self.subTest(origin=origin), patch.dict(os.environ, {"PUBLIC_SITE_ORIGIN": origin}, clear=False):
                with self.assertRaises(ValueError):
                    PublicSiteSettings.from_env()

    def test_configured_origin_not_request_host_controls_canonical_urls(self) -> None:
        with patch.dict(os.environ, {"PUBLIC_SITE_ORIGIN": "https://public.example.test", "PUBLIC_SITE_NAME": "Library", "PUBLIC_SITE_DESCRIPTION": "A library"}, clear=False):
            import triage_processor.public_site.rendering as rendering
            importlib.reload(rendering)
            page = rendering.layout("Home", "<h1>Home</h1>", "/")
            self.assertIn('href="https://public.example.test/"', page)
            self.assertNotIn("attacker.example", page)
        importlib.reload(rendering)

    def test_public_edge_declares_short_html_and_immutable_hashed_asset_caching(self) -> None:
        root = Path(__file__).resolve().parents[2]
        if not (root / "frontend").exists():
            root = Path("/workspace")
        nginx = (root / "frontend/public/nginx/default.conf").read_text()
        headers = (root / "frontend/public/nginx/security-headers.inc").read_text()
        self.assertIn('Cache-Control "public, max-age=300"', nginx)
        self.assertIn('Cache-Control "public, max-age=31536000, immutable"', nginx)
        self.assertIn("proxy_intercept_errors on;", nginx)
        self.assertIn("location @public_server_error", nginx)
        self.assertNotIn("traceback", nginx.lower())
        for header in ("Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy", "frame-ancestors 'none'", "script-src 'none'", "connect-src 'none'"):
            self.assertIn(header, headers)
