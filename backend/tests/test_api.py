import unittest

from triage_processor.api.main import app


class ApiStructureTests(unittest.TestCase):
    def test_inputs_route_is_registered(self):
        self.assertIn("/inputs", app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
