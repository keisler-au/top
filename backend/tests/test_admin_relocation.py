"""Static topology checks for the relocated internal admin dashboard."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "compose.yaml").exists():
    ROOT = Path("/")


class AdminRelocationTests(unittest.TestCase):
    def test_admin_application_is_self_contained_under_frontend_admin(self) -> None:
        admin = ROOT / "frontend/admin"
        if not admin.exists():
            admin = Path("/workspace/frontend/admin")
        for path in (
            "package.json", "package-lock.json", "tsconfig.json", "Dockerfile",
            "README.md", "index.html", "src", "tests", "scripts", "nginx",
        ):
            with self.subTest(path=path):
                self.assertTrue((admin / path).exists())

    def test_admin_service_is_opt_in_and_loopback_only(self) -> None:
        compose = (ROOT / "compose.yaml").read_text()
        service = compose[compose.index("  admin-web:"):compose.index("  google-sheets:")]
        self.assertIn('profiles: ["admin"]', service)
        self.assertIn("context: ./frontend/admin", service)
        self.assertIn('127.0.0.1:${ADMIN_PORT:-8081}:8080', service)
        self.assertNotIn("  frontend:\n", compose)

