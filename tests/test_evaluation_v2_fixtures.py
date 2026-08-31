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
            "S02-DEV-001",
            "S03-DEV-001",
            "S04-DEV-001",
            "S05A-DEV-001",
            "S05B-DEV-001",
            "S06-DEV-001",
            "S07-DEV-001",
            "S09A-DEV-001",
            "S09B-DEV-001",
            "S10-DEV-001",
            "S10-DEV-002",
            "S11-DEV-001",
            "S11-DEV-002",
        ])
        self.assertEqual(sum(item["source_count"] for item in result), 15)

    def test_package_rejects_path_outside_repository(self):
        # CI의 체크아웃은 컨테이너 appuser에게 읽기 전용일 수 있다. 이 검증은
        # 합성 package 경계만 필요하므로 쓰기 가능한 시스템 임시 경로를 쓴다.
        with tempfile.TemporaryDirectory() as temporary:
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

    def test_s07_adversarial_tool_profile_is_not_labeled_as_deployment(self):
        import yaml

        fixture = yaml.safe_load(
            (FIXTURES_ROOT / "S07-DEV-001" / "fixture.yaml").read_text(encoding="utf-8")
        )
        environment = fixture["environment_identity"]
        self.assertEqual(environment["tool_profile_id"], "EVAL_S07_TOOL_PROFILE_V2")
        self.assertFalse(environment["deployment_equivalent"])
        self.assertIn("task_register", fixture["forbidden_tools"])


if __name__ == "__main__":
    unittest.main()
