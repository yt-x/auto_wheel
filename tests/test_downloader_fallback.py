import subprocess
import tempfile
import unittest
from unittest.mock import patch

from auto_wheel.downloader import WheelDownloader


class WheelDownloaderFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.downloader = WheelDownloader(
            python_version="3.9",
            output_dir=self.temp_dir.name,
            only_binary=":all:",
            max_attempts=1,
            retry_delay=0.0,
            command_timeout=60,
        )

    def test_wheel_only_success_without_fallback(self):
        success = subprocess.CompletedProcess(
            args=["python", "-m", "pip", "download"],
            returncode=0,
            stdout="ok",
            stderr="",
        )
        with patch("auto_wheel.downloader.subprocess.run", side_effect=[success]) as mocked_run:
            result = self.downloader.download_packages(["demo==1.0.0"])

        self.assertTrue(result["success"])
        self.assertFalse(result["used_source_fallback"])
        self.assertIsNone(result["fallback_reason"])
        self.assertEqual(mocked_run.call_count, 1)
        first_cmd = mocked_run.call_args_list[0][0][0]
        self.assertIn("--only-binary", first_cmd)

    def test_trigger_fallback_when_no_wheel_then_success(self):
        no_wheel = subprocess.CalledProcessError(
            returncode=1,
            cmd=["python", "-m", "pip", "download"],
            output="",
            stderr="ERROR: No matching distribution found for demo==1.0.0",
        )
        success = subprocess.CompletedProcess(
            args=["python", "-m", "pip", "download"],
            returncode=0,
            stdout="fallback ok",
            stderr="",
        )

        with patch("auto_wheel.downloader.subprocess.run", side_effect=[no_wheel, success]) as mocked_run:
            result = self.downloader.download_packages(["demo==1.0.0"])

        self.assertTrue(result["success"])
        self.assertTrue(result["used_source_fallback"])
        self.assertIn("wheel", result["fallback_reason"].lower())
        self.assertEqual(mocked_run.call_count, 2)
        first_cmd = mocked_run.call_args_list[0][0][0]
        second_cmd = mocked_run.call_args_list[1][0][0]
        self.assertIn("--only-binary", first_cmd)
        self.assertNotIn("--only-binary", second_cmd)
        self.assertNotIn("--python-version", second_cmd)
        self.assertNotIn("--implementation", second_cmd)
        self.assertNotIn("--abi", second_cmd)

    def test_source_fallback_command_removes_target_constraints(self):
        cmd = [
            "python", "-m", "pip", "download",
            "--dest", "downloads",
            "--python-version", "3.9",
            "--platform", "manylinux2014_x86_64",
            "--implementation", "cp",
            "--abi", "cp39",
            "--only-binary", ":all:",
            "-r", "req.txt",
        ]
        fallback_cmd = self.downloader._build_source_fallback_command(cmd, source_fallback_no_deps=False)
        self.assertNotIn("--only-binary", fallback_cmd)
        self.assertNotIn("--python-version", fallback_cmd)
        self.assertNotIn("--platform", fallback_cmd)
        self.assertNotIn("--implementation", fallback_cmd)
        self.assertNotIn("--abi", fallback_cmd)
        self.assertIn("-r", fallback_cmd)
        self.assertNotIn("--no-deps", fallback_cmd)

    def test_resolved_requirements_fallback_adds_no_deps(self):
        no_wheel = subprocess.CalledProcessError(
            returncode=1,
            cmd=["python", "-m", "pip", "download"],
            output="",
            stderr="ERROR: No matching distribution found for demo==1.0.0",
        )
        success = subprocess.CompletedProcess(
            args=["python", "-m", "pip", "download"],
            returncode=0,
            stdout="fallback ok",
            stderr="",
        )
        with patch("auto_wheel.downloader.subprocess.run", side_effect=[no_wheel, success]) as mocked_run:
            result = self.downloader.download_resolved_requirements(["demo==1.0.0"])

        self.assertTrue(result["success"])
        self.assertTrue(result["used_source_fallback"])
        self.assertEqual(mocked_run.call_count, 2)
        second_cmd = mocked_run.call_args_list[1][0][0]
        self.assertIn("--no-deps", second_cmd)

    def test_non_no_wheel_error_should_not_trigger_fallback(self):
        network_error = subprocess.CalledProcessError(
            returncode=1,
            cmd=["python", "-m", "pip", "download"],
            output="",
            stderr="ERROR: HTTPSConnectionPool(host='pypi.org', port=443): Read timed out.",
        )

        with patch("auto_wheel.downloader.subprocess.run", side_effect=[network_error]) as mocked_run:
            result = self.downloader.download_packages(["demo==1.0.0"])

        self.assertFalse(result["success"])
        self.assertFalse(result["used_source_fallback"])
        self.assertIsNone(result["fallback_reason"])
        self.assertEqual(mocked_run.call_count, 1)

    def test_detect_no_wheel_reason_for_environment_message(self):
        errors = [
            {
                "message": "resolver failed",
                "stderr": "Additionally, some packages in these conflicts have no matching distributions available for your environment: thrift",
                "stdout": "",
            }
        ]
        reason = self.downloader._detect_no_wheel_reason(errors)
        self.assertIsNotNone(reason)
        self.assertIn("wheel", reason.lower())

    def test_fallback_failure_keeps_two_stage_errors(self):
        no_wheel = subprocess.CalledProcessError(
            returncode=1,
            cmd=["python", "-m", "pip", "download"],
            output="",
            stderr="ERROR: No matching distribution found for demo==1.0.0",
        )
        fallback_failed = subprocess.CalledProcessError(
            returncode=1,
            cmd=["python", "-m", "pip", "download"],
            output="",
            stderr="ERROR: Could not build wheels for demo",
        )

        with patch("auto_wheel.downloader.subprocess.run", side_effect=[no_wheel, fallback_failed]) as mocked_run:
            result = self.downloader.download_packages(["demo==1.0.0"])

        self.assertFalse(result["success"])
        self.assertTrue(result["used_source_fallback"])
        self.assertEqual(mocked_run.call_count, 2)
        stages = {item.get("stage") for item in result.get("errors", [])}
        self.assertIn("wheel_only", stages)
        self.assertIn("source_fallback", stages)


if __name__ == "__main__":
    unittest.main()
