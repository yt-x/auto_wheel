import json
import unittest
from pathlib import Path

from auto_wheel.requirements_generator import RequirementsGenerator


class ManifestGenerationTests(unittest.TestCase):
    def setUp(self):
        self.work_dir = Path(__file__).resolve().parent.parent / ".tmp_tests"
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _make_case_dir(self, case_name: str) -> Path:
        case_dir = self.work_dir / case_name
        if case_dir.exists():
            for child in case_dir.rglob("*"):
                if child.is_file():
                    child.unlink()
            for child in sorted(case_dir.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def test_lock_mode_should_use_resolved_requirements_and_ignore_extra_wheels(self):
        out_dir = self._make_case_dir("lock_ignore_extra")
        # 模拟目录中存在历史残留更高版本
        (out_dir / "sqlalchemy-2.0.49-py3-none-any.whl").write_bytes(b"legacy")
        (out_dir / "sqlalchemy-2.0.40-py3-none-any.whl").write_bytes(b"locked")
        (out_dir / "typing_extensions-4.12.2-py3-none-any.whl").write_bytes(b"dep")

        generator = RequirementsGenerator(output_dir=str(out_dir), with_hashes=False)
        req_file = generator.generate(
            resolved_requirements=[
                "sqlalchemy==2.0.40",
                "typing_extensions==4.12.2",
            ]
        )

        content = Path(req_file).read_text(encoding="utf-8")
        self.assertIn("Manifest mode: lock", content)
        self.assertIn("sqlalchemy==2.0.40", content)
        self.assertNotIn("sqlalchemy==2.0.49", content)

        reconciliation_file = generator.last_summary["reconciliation_file"]
        payload = json.loads(Path(reconciliation_file).read_text(encoding="utf-8"))
        self.assertEqual(payload["manifest_mode"], "lock")
        self.assertIn("sqlalchemy==2.0.49", payload["extra_artifacts_not_in_lock"])

    def test_non_lock_mode_should_scan_wheels_and_mark_mode(self):
        out_dir = self._make_case_dir("non_lock_scan")
        (out_dir / "requests-2.31.0-py3-none-any.whl").write_bytes(b"x")

        generator = RequirementsGenerator(output_dir=str(out_dir), with_hashes=False)
        req_file = generator.generate()
        content = Path(req_file).read_text(encoding="utf-8")

        self.assertIn("Manifest mode: non_lock", content)
        self.assertIn("requests==2.31.0", content)

        payload = json.loads(Path(generator.last_summary["reconciliation_file"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["manifest_mode"], "non_lock")
        self.assertEqual(payload["lock_requirements"], [])

    def test_lock_mode_with_hashes_should_keep_hash_lines_when_wheel_exists(self):
        out_dir = self._make_case_dir("lock_hash")
        wheel_file = out_dir / "requests-2.31.0-py3-none-any.whl"
        wheel_file.write_bytes(b"wheel-content")

        generator = RequirementsGenerator(output_dir=str(out_dir), with_hashes=True)
        req_file = generator.generate(resolved_requirements=["requests==2.31.0"])
        content = Path(req_file).read_text(encoding="utf-8")

        self.assertIn("requests==2.31.0 \\", content)
        self.assertIn("--hash=sha256:", content)


if __name__ == "__main__":
    unittest.main()
