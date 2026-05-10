import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auto_wheel.requirements_generator import RequirementsGenerator


class InstallabilityCheckTests(unittest.TestCase):
    def test_installability_report_pass(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            generator = RequirementsGenerator(output_dir=tmp_dir, with_hashes=False)
            (Path(tmp_dir) / "requirements-offline.txt").write_text("requests==2.31.0\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=["python", "-m", "pip", "install"],
                returncode=0,
                stdout="Would install requests",
                stderr="",
            )
            with patch("auto_wheel.requirements_generator.subprocess.run", return_value=completed):
                result = generator.run_installability_check(context={"python_version": "3.9"})

            self.assertTrue(result["success"])
            report_path = Path(result["report_file"])
            self.assertTrue(report_path.exists())
            content = report_path.read_text(encoding="utf-8")
            self.assertIn("PASS", content)
            self.assertIn("python_version", content)

    def test_installability_report_fail(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            generator = RequirementsGenerator(output_dir=tmp_dir, with_hashes=False)
            (Path(tmp_dir) / "requirements-offline.txt").write_text("broken==1.0.0\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=["python", "-m", "pip", "install"],
                returncode=1,
                stdout="",
                stderr="No matching distribution found",
            )
            with patch("auto_wheel.requirements_generator.subprocess.run", return_value=completed):
                result = generator.run_installability_check()

            self.assertFalse(result["success"])
            report_path = Path(result["report_file"])
            content = report_path.read_text(encoding="utf-8")
            self.assertIn("FAIL", content)
            self.assertIn("No matching distribution found", content)


if __name__ == "__main__":
    unittest.main()
