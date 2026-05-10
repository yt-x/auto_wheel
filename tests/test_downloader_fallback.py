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
            use_uv_resolver=True,
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

        with patch("auto_wheel.downloader.subprocess.run", side_effect=[no_wheel]) as mocked_run:
            with patch.object(
                self.downloader,
                "_probe_wheel_availability",
                return_value={"status": "no_wheel", "reason": "No wheel available"},
            ):
                with patch.object(
                    self.downloader,
                    "_execute_separate_strategy",
                    return_value={
                        "success": True,
                        "used_source_fallback": True,
                        "fallback_reason": "No wheel available",
                        "source_packages": ["demo==1.0.0"],
                    },
                ) as mocked_separate:
                    result = self.downloader.download_packages(["demo==1.0.0"])

        self.assertTrue(result["success"])
        self.assertTrue(result["used_source_fallback"])
        self.assertIn("wheel", result["fallback_reason"].lower())
        mocked_separate.assert_called_once()

    def test_source_fallback_command_builds_correctly_for_uv_path(self):
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
        fallback_cmd = self.downloader._build_source_fallback_command(cmd, source_fallback_no_deps=True)
        self.assertNotIn("--only-binary", fallback_cmd)
        self.assertIn("--python-version", fallback_cmd)
        self.assertNotIn("--platform", fallback_cmd)
        self.assertNotIn("--implementation", fallback_cmd)
        self.assertNotIn("--abi", fallback_cmd)
        self.assertIn("--no-deps", fallback_cmd)
        self.assertIn("-r", fallback_cmd)

    def test_source_fallback_command_builds_correctly_for_raw_path(self):
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
        self.assertNotIn("--no-deps", fallback_cmd)
        self.assertIn("-r", fallback_cmd)

    def test_resolved_requirements_fallback_triggers_separate_strategy(self):
        no_wheel = subprocess.CalledProcessError(
            returncode=1,
            cmd=["python", "-m", "pip", "download"],
            output="",
            stderr="ERROR: No matching distribution found for demo==1.0.0",
        )
        with patch("auto_wheel.downloader.subprocess.run", side_effect=[no_wheel]) as mocked_run:
            with patch.object(
                self.downloader,
                "_probe_wheel_availability",
                return_value={"status": "no_wheel", "reason": "No wheel available"},
            ):
                with patch.object(
                    self.downloader,
                    "_execute_separate_strategy",
                    return_value={
                        "success": True,
                        "used_source_fallback": True,
                        "fallback_reason": "No wheel available",
                        "source_packages": ["demo==1.0.0"],
                    },
                ) as mocked_separate:
                    result = self.downloader.download_resolved_requirements(["demo==1.0.0"])

        self.assertTrue(result["success"])
        self.assertTrue(result["used_source_fallback"])
        mocked_separate.assert_called_once()
        call_kwargs = mocked_separate.call_args.kwargs
        self.assertTrue(call_kwargs.get("source_fallback_no_deps", True))

    def test_source_package_separate_command_has_no_deps(self):
        cmd = self.downloader._build_pip_command(["demo==1.0.0"], dry_run=False)
        source_cmd = self.downloader._build_source_fallback_command(cmd, source_fallback_no_deps=True)
        self.assertIn("--no-deps", source_cmd)

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

    def test_fallback_failure_keeps_errors(self):
        no_wheel = subprocess.CalledProcessError(
            returncode=1,
            cmd=["python", "-m", "pip", "download"],
            output="",
            stderr="ERROR: No matching distribution found for demo==1.0.0",
        )

        with patch("auto_wheel.downloader.subprocess.run", side_effect=[no_wheel]) as mocked_run:
            with patch.object(
                self.downloader,
                "_probe_wheel_availability",
                return_value={"status": "no_wheel", "reason": "No wheel available"},
            ):
                with patch.object(
                    self.downloader,
                    "_execute_separate_strategy",
                    return_value={
                        "success": False,
                        "error": "Source fallback failed",
                        "errors": [
                            {"stage": "wheel_only", "stderr": "No matching distribution"},
                            {"stage": "source_separate", "stderr": "build failed"},
                        ],
                        "used_source_fallback": True,
                        "fallback_reason": "No wheel available",
                    },
                ):
                    result = self.downloader.download_packages(["demo==1.0.0"])

        self.assertFalse(result["success"])
        self.assertTrue(result["used_source_fallback"])
        stages = {item.get("stage") for item in result.get("errors", [])}
        self.assertIn("wheel_only", stages)
        self.assertIn("source_separate", stages)


if __name__ == "__main__":
    unittest.main()
