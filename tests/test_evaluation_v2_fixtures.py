import tempfile
import unittest
from pathlib import Path

from services.evaluation.v2_fixtures import validate_fixture_package, validate_fixture_tree


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = (
    REPO_ROOT
    / "docs"
    / "설계 및 구현"
    / "3_중간발표 이후"
    / "설계"
    / "eval"
    / "v2"
    / "fixtures"
    / "dev"
)


class EvaluationV2FixtureTests(unittest.TestCase):
    def test_all_dev_packages_match_existing_pdf_hashes_and_gold(self):
        result = validate_fixture_tree(FIXTURES_ROOT, repo_root=REPO_ROOT)
        self.assertEqual([item["fixture_id"] for item in result], [
            "S01-DEV-001",
            "S04-DEV-001",
            "S07-DEV-001",
            "S09A-DEV-001",
        ])
        self.assertEqual(sum(item["source_count"] for item in result), 7)

    def test_package_rejects_path_outside_repository(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            package = Path(temporary) / "BAD"
            package.mkdir()
            (package / "fixture.yaml").write_text(
                "fixture_id: BAD\nfixture_version: 1\ngold_version: 1\n"
                "source_artifacts:\n  - source_id: X\n    repo_path: ../outside.pdf\n"
                "    sha256: bad\n",
                encoding="utf-8",
            )
            (package / "gold.yaml").write_text(
                "gold_identity:\n  fixture_id: BAD\n  fixture_version: 1\n  gold_version: 1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "저장소 밖|source 파일"):
                validate_fixture_package(package, repo_root=package)


if __name__ == "__main__":
    unittest.main()
