import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import importlib.util
import sys
import types


_WORKERS_PATH = Path(__file__).resolve().parent.parent / "src" / "auto_wheel" / "gui" / "workers.py"
_SPEC = importlib.util.spec_from_file_location("auto_wheel.gui.workers", _WORKERS_PATH)
_WORKERS = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader

# 为无 PyQt6 环境提供最小替身，避免导入失败
if "PyQt6" not in sys.modules:
    pyqt6_mod = types.ModuleType("PyQt6")
    qtcore_mod = types.ModuleType("PyQt6.QtCore")

    class _DummyQThread:
        def __init__(self, parent=None):
            self.parent = parent

    class _DummySignal:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def emit(self, *args, **kwargs):
            return None

    def _dummy_pyqt_signal(*args, **kwargs):
        return _DummySignal(*args, **kwargs)

    qtcore_mod.QThread = _DummyQThread
    qtcore_mod.pyqtSignal = _dummy_pyqt_signal
    pyqt6_mod.QtCore = qtcore_mod
    sys.modules["PyQt6"] = pyqt6_mod
    sys.modules["PyQt6.QtCore"] = qtcore_mod

sys.modules["auto_wheel.gui.workers"] = _WORKERS
_SPEC.loader.exec_module(_WORKERS)

DownloadRequest = _WORKERS.DownloadRequest
DownloadWorker = _WORKERS.DownloadWorker


class GuiWorkerManifestModeTests(unittest.TestCase):
    def _build_request(self, tmp_dir: str) -> DownloadRequest:
        return DownloadRequest(
            source_mode="packages",
            requirements_path=None,
            packages=["requests==2.31.0"],
            python_version="3.9",
            output_dir=tmp_dir,
            config_path=None,
            platform="auto",
            implementation="cp",
            abi=None,
            only_binary=":all:",
            with_hashes=False,
            verbose=False,
            dry_run=False,
            retries=1,
            timeout=60,
            plan_only=False,
            require_tree_approval=False,
            tree_approved=False,
        )

    def test_worker_should_pass_lock_requirements_to_generator(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            req = self._build_request(tmp_dir)
            worker = DownloadWorker(request=req)
            worker.log_message = MagicMock()
            worker.finished = MagicMock()

            fake_config = MagicMock()
            fake_config.get.side_effect = lambda key, default=None: default
            fake_config.download_dir = tmp_dir
            fake_config.get_pip_args.return_value = []
            fake_config.use_uv_resolver = True

            fake_resolver = MagicMock()
            fake_resolver.resolve.return_value = (["requests==2.31.0"], True, None)
            fake_resolver.get_last_resolution_state.return_value = {
                "job_state": "planning_ready",
                "stage": "uv_compile",
                "resolver": "uv",
            }

            fake_downloader = MagicMock()
            fake_downloader.download_resolved_requirements.return_value = {"success": True, "output": ""}

            fake_generator = MagicMock()
            req_file = str(Path(tmp_dir) / "requirements-offline.txt")
            Path(req_file).write_text("requests==2.31.0\n", encoding="utf-8")
            fake_generator.generate.return_value = req_file
            fake_generator.generate_install_script.return_value = str(Path(tmp_dir) / "install.sh")
            fake_generator.last_summary = {
                "manifest_mode": "lock",
                "reconciliation_file": str(Path(tmp_dir) / "manifest-reconciliation.json"),
            }

            with patch.object(_WORKERS, "Config", return_value=fake_config):
                with patch.object(_WORKERS, "DependencyResolver", return_value=fake_resolver):
                    with patch.object(_WORKERS, "WheelDownloader", return_value=fake_downloader):
                        with patch.object(_WORKERS, "RequirementsGenerator", return_value=fake_generator):
                            with patch.object(_WORKERS, "_count_manifest_entries", return_value=0):
                                worker._perform()

            fake_generator.generate.assert_called_once_with(
                resolved_requirements=["requests==2.31.0"]
            )


if __name__ == "__main__":
    unittest.main()
