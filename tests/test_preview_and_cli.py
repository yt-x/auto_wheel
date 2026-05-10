import json
import tempfile
import unittest
from pathlib import Path

from auto_wheel.cli import parse_arguments, validate_arguments
from auto_wheel.requirements_generator import RequirementsGenerator


class PreviewAndCliTests(unittest.TestCase):
    def test_generate_dependency_preview_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            generator = RequirementsGenerator(output_dir=tmp_dir, with_hashes=False)
            preview = generator.generate_dependency_preview(
                requirements=["requests==2.31.0", "urllib3>=1.26"],
                python_version="3.9",
                platform="manylinux2014_x86_64",
                implementation="cp",
                abi="cp39",
                resolver_state={"job_state": "planning_ready", "stage": "uv_compile"},
            )

            tree_json = Path(preview["tree_json"])
            tree_text = Path(preview["tree_text"])
            coverage = Path(preview["coverage_report"])
            self.assertTrue(tree_json.exists())
            self.assertTrue(tree_text.exists())
            self.assertTrue(coverage.exists())

            payload = json.loads(tree_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["target"]["python_version"], "3.9")
            self.assertEqual(len(payload["dependencies"]), 2)
            self.assertEqual(payload["dependencies"][0]["state"], "resolved")

    def test_plan_only_and_approve_tree_are_mutually_exclusive(self):
        args = parse_arguments(["-pkg", "requests==2.31.0", "--plan-only", "--approve-tree", "tree.json"])
        with self.assertRaises(ValueError):
            validate_arguments(args)

    def test_approve_tree_file_must_exist(self):
        args = parse_arguments(["-pkg", "requests==2.31.0", "--approve-tree", "not-found-tree.json"])
        with self.assertRaises(ValueError):
            validate_arguments(args)


if __name__ == "__main__":
    unittest.main()
