import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_repo import forbidden_path, text_findings


class RepositoryPolicyTests(unittest.TestCase):
    def test_local_credentials_are_rejected(self):
        for path in (".env", "app/.env.production", ".config.env", "app/data/snapshot.json", "이음온_상담준비.txt"):
            self.assertIsNotNone(forbidden_path(path), path)

    def test_examples_and_source_are_allowed(self):
        for path in (".env.example", "app/.env.example", ".github/workflows/repository-hygiene.yml", "app/server.py"):
            self.assertIsNone(forbidden_path(path), path)

    def test_embedded_key_is_rejected_even_in_example(self):
        synthetic = "sk-cody-" + "live-" + "A" * 30
        self.assertIn("Codyssey key", text_findings(synthetic))

    def test_placeholder_is_allowed(self):
        self.assertEqual(text_findings("LLM_API_KEY=your_virtual_key"), [])

    def test_merge_conflict_is_rejected(self):
        marker = "<" * 7 + " HEAD\nx\n" + "=" * 7 + "\ny\n" + ">" * 7 + " feature"
        self.assertIn("unresolved merge conflict", text_findings(marker))


if __name__ == "__main__":
    unittest.main()

