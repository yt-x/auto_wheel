import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from auto_wheel import main as main_module


class MainVerifyExitTests(unittest.TestCase):
    def test_verify_installability_failure_exits_with_code_2(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = argparse.Namespace(
                requirements=None,
                packages=["requests==2.31.0"],
                python_version="3.9",
                output=tmp_dir,
                config=None,
                platform="auto",
                implementation="cp",
                abi=None,
                only_binary=":all:",
                verbose=False,
                with_hashes=False,
                dry_run=False,
                plan_only=False,
                approve_tree=None,
                verify_installability=True,
            )

            fake_config = MagicMock()
            fake_config.get.side_effect = lambda key, default=None: default
            fake_config.download_dir = tmp_dir
            fake_config.index_url = ""
            fake_config.get_pip_args.return_value = []
            fake_config.retries = 1
            fake_config.pip_timeout = 60
            fake_config.timeout = 60
            fake_config.use_uv_resolver = False

            fake_downloader = MagicMock()
            fake_downloader.download_packages.return_value = {
                "success": True,
                "errors": [],
                "used_source_fallback": False,
            }

            fake_resolver = MagicMock()
            fake_resolver.resolve.return_value = (["requests==2.31.0"], False, None)
            fake_resolver.get_last_resolution_state.return_value = {
                "job_state": "planning_ready",
                "stage": "pip_direct",
                "resolver": "pip",
            }

            fake_generator = MagicMock()
            req_file = str(Path(tmp_dir) / "requirements-offline.txt")
            Path(req_file).write_text("requests==2.31.0\n", encoding="utf-8")
            fake_generator.generate.return_value = req_file
            fake_generator.generate_install_script.return_value = str(Path(tmp_dir) / "install.sh")
            fake_generator.run_installability_check.return_value = {
                "success": False,
                "report_file": str(Path(tmp_dir) / "installability-report.md"),
            }

            with patch("auto_wheel.main.parse_arguments", return_value=args):
                with patch("auto_wheel.main.validate_arguments", return_value=None):
                    with patch("auto_wheel.main.Config", return_value=fake_config):
                        with patch("auto_wheel.main.WheelDownloader", return_value=fake_downloader):
                            with patch("auto_wheel.main.DependencyResolver", return_value=fake_resolver):
                                with patch("auto_wheel.main.RequirementsGenerator", return_value=fake_generator):
                                    with self.assertRaises(SystemExit) as cm:
                                        main_module.main()

            self.assertEqual(cm.exception.code, 2)
            fake_generator.generate.assert_called_once_with(resolved_requirements=None)


if __name__ == "__main__":
    unittest.main()
