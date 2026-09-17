"""Static boundary checks for the retired incremental taxonomy runtime."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
if not COMPOSE.exists():
    COMPOSE = Path("/compose.yaml")
SOURCE = ROOT / "backend/src/triage_processor"
if not SOURCE.exists():
    SOURCE = Path("/app/src/triage_processor")


class LegacyTaxonomyRetirementTests(unittest.TestCase):
    def test_retired_worker_modules_and_compose_services_are_absent(self) -> None:
        self.assertFalse((SOURCE / "workers/topics.py").exists())
        self.assertFalse((SOURCE / "workers/themes.py").exists())
        compose = COMPOSE.read_text()
        self.assertNotIn("  topics:\n", compose)
        self.assertNotIn("  themes:\n", compose)

    def test_runtime_code_has_no_legacy_queue_or_reader_fallback(self) -> None:
        forbidden = (
            "workers.topics",
            "workers.themes",
            "job_type IN ('topics', 'themes')",
            "FROM themes WHERE",
            "JOIN themes ON",
            "segments.topic",
            "inputs.topic",
            "source_inputs.topic",
        )
        excluded = {SOURCE / "api/routes/taxonomy_legacy_archive.py"}
        for path in SOURCE.rglob("*.py"):
            if path in excluded:
                continue
            source = path.read_text()
            for token in forbidden:
                with self.subTest(path=path.relative_to(SOURCE), token=token):
                    self.assertNotIn(token, source)

    def test_only_the_protected_archive_route_names_legacy_relations(self) -> None:
        archive_route = SOURCE / "api/routes/taxonomy_legacy_archive.py"
        self.assertTrue(archive_route.exists())
        route_source = archive_route.read_text()
        self.assertIn("taxonomy_legacy_archive", route_source)
        self.assertNotIn("original_inputs", route_source)
        self.assertNotIn("segment_inputs", route_source)
