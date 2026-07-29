"""
Config 加载与查找顺序测试。

优先级链（高 -> 低）：
    CLI/GUI 显式值 > -c 指定文件 > ./config.json > 用户级配置 > 程序默认值
本文件只测试 Config 负责的文件解析部分（-c / CWD / 用户级 / 默认值）。
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auto_wheel.config import Config, default_user_config_path


class ConfigLookupOrderTest(unittest.TestCase):
    """验证配置文件查找顺序：-c > ./config.json > 用户级 > 默认值。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work_dir = Path(self._tmp.name) / "work"
        self.work_dir.mkdir(parents=True)
        self.user_dir = Path(self._tmp.name) / "user"
        self.user_dir.mkdir(parents=True)
        self.user_config = self.user_dir / "config.json"

        # 隔离 CWD，避免读到仓库根目录的真实 config.json
        self._old_cwd = os.getcwd()
        os.chdir(str(self.work_dir))
        self.addCleanup(os.chdir, self._old_cwd)

        # 将用户级配置路径指向临时目录
        patcher = mock.patch(
            "auto_wheel.config.default_user_config_path",
            return_value=self.user_config,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_json(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_defaults_when_no_config_found(self) -> None:
        config = Config()
        self.assertEqual(config.config_data, Config.DEFAULT_CONFIG)
        self.assertIsNone(config.loaded_from)

    def test_cwd_config_loaded(self) -> None:
        self._write_json(self.work_dir / "config.json", {"retries": 5})
        config = Config()
        self.assertEqual(config.retries, 5)
        self.assertEqual(config.loaded_from, "config.json")
        # 未覆盖的键保持默认值
        self.assertEqual(config.pip_timeout, Config.DEFAULT_CONFIG["pip_timeout"])

    def test_user_config_fallback_when_cwd_missing(self) -> None:
        self._write_json(self.user_config, {"retries": 7, "index_url": "https://example.com/simple"})
        config = Config()
        self.assertEqual(config.retries, 7)
        self.assertEqual(config.index_url, "https://example.com/simple")
        self.assertEqual(config.loaded_from, str(self.user_config))

    def test_cwd_config_wins_over_user_config(self) -> None:
        self._write_json(self.work_dir / "config.json", {"retries": 2})
        self._write_json(self.user_config, {"retries": 7})
        config = Config()
        self.assertEqual(config.retries, 2)
        self.assertEqual(config.loaded_from, "config.json")

    def test_explicit_path_wins_over_all(self) -> None:
        explicit = Path(self._tmp.name) / "explicit.json"
        self._write_json(explicit, {"retries": 9})
        self._write_json(self.work_dir / "config.json", {"retries": 2})
        self._write_json(self.user_config, {"retries": 7})
        config = Config(config_path=str(explicit))
        self.assertEqual(config.retries, 9)
        self.assertEqual(config.loaded_from, str(explicit))

    def test_partial_user_config_merges_with_defaults(self) -> None:
        self._write_json(self.user_config, {"index_url": "https://mirror.example.com/simple"})
        config = Config()
        self.assertEqual(config.index_url, "https://mirror.example.com/simple")
        self.assertEqual(config.retries, Config.DEFAULT_CONFIG["retries"])
        self.assertTrue(config.use_uv_resolver)

    def test_invalid_json_falls_back_to_defaults(self) -> None:
        (self.work_dir / "config.json").write_text("{invalid json", encoding="utf-8")
        config = Config()
        self.assertEqual(config.config_data, Config.DEFAULT_CONFIG)
        self.assertIsNone(config.loaded_from)

    def test_missing_explicit_path_falls_back_to_defaults(self) -> None:
        config = Config(config_path=str(Path(self._tmp.name) / "nonexistent.json"))
        self.assertEqual(config.config_data, Config.DEFAULT_CONFIG)
        self.assertIsNone(config.loaded_from)


class DefaultUserConfigPathTest(unittest.TestCase):
    """验证用户级配置路径的平台推导逻辑（仅测试当前平台分支）。"""

    @unittest.skipUnless(os.name == "nt", "Windows 专属分支")
    def test_windows_uses_appdata(self) -> None:
        with mock.patch.dict(
            os.environ, {"APPDATA": r"C:\Users\test\AppData\Roaming"}
        ):
            path = default_user_config_path()
            self.assertEqual(path, Path(r"C:\Users\test\AppData\Roaming") / "auto_wheel" / "config.json")

    @unittest.skipUnless(os.name == "nt", "Windows 专属分支")
    def test_windows_fallback_to_home_dot_config(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "APPDATA"}
        with mock.patch.dict(os.environ, env, clear=True):
            path = default_user_config_path()
            self.assertEqual(path, Path.home() / ".config" / "auto_wheel" / "config.json")

    @unittest.skipIf(os.name == "nt", "POSIX 专属分支")
    def test_posix_uses_xdg_config_home(self) -> None:
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/xdg"}):
            path = default_user_config_path()
            self.assertEqual(path, Path("/tmp/xdg") / "auto_wheel" / "config.json")

    @unittest.skipIf(os.name == "nt", "POSIX 专属分支")
    def test_posix_fallback_to_home_dot_config(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        with mock.patch.dict(os.environ, env, clear=True):
            path = default_user_config_path()
            self.assertEqual(path, Path.home() / ".config" / "auto_wheel" / "config.json")


if __name__ == "__main__":
    unittest.main()
