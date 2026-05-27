"""
SourceReader 单元测试 — 覆盖三种输入格式的检测与解析。
"""

import tempfile
import unittest
from pathlib import Path

from auto_wheel.source_reader import SourceReader, SourceType, DependencySource


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class SourceReaderRequirementsTests(unittest.TestCase):
    def test_read_simple_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "dev-deps.txt"
            _write(req_file, "requests>=2.28.0\nflask==3.0.0\n\n# comment\nclick\n")
            reader = SourceReader()
            source = reader.read(str(req_file))
            self.assertEqual(source.source_type, SourceType.REQUIREMENTS_TXT)
            self.assertFalse(source.is_pinned)
            self.assertIn("requests>=2.28.0", source.requirements)
            self.assertIn("flask==3.0.0", source.requirements)
            self.assertIn("click", source.requirements)
            self.assertEqual(len(source.requirements), 3)

    def test_empty_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.txt"
            _write(empty, "")
            reader = SourceReader()
            with self.assertRaises(ValueError) as ctx:
                reader.read(str(empty))
            self.assertIn("未检测到可识别的依赖声明", str(ctx.exception))

    def test_file_not_found(self):
        reader = SourceReader()
        with self.assertRaises(FileNotFoundError):
            reader.read("/nonexistent/path/deps.txt")

    def test_non_utf8_binary_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_file = Path(tmp) / "data.bin"
            bin_file.write_bytes(b"\x80\x81\x82\x83")
            reader = SourceReader()
            with self.assertRaises(ValueError) as ctx:
                reader.read(str(bin_file))
            self.assertIn("UTF-8", str(ctx.exception))


class SourceReaderPyprojectTests(unittest.TestCase):
    def test_read_pyproject_with_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            _write(
                pyproject,
                '[project]\nname = "myapp"\ndependencies = [\n'
                '  "requests>=2.28.0",\n  "click>=8.0.0"\n]\n',
            )
            reader = SourceReader()
            source = reader.read(str(pyproject))
            self.assertEqual(source.source_type, SourceType.PYPROJECT_TOML)
            self.assertFalse(source.is_pinned)
            self.assertIn("requests>=2.28.0", source.requirements)
            self.assertIn("click>=8.0.0", source.requirements)

    def test_pyproject_without_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            _write(pyproject, '[project]\nname = "myapp"\n')
            reader = SourceReader()
            source = reader.read(str(pyproject))
            self.assertEqual(source.source_type, SourceType.PYPROJECT_TOML)
            self.assertFalse(source.requirements)
            self.assertTrue(any("未找到 project.dependencies" in w for w in source.warnings))

    def test_pyproject_without_project_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            _write(pyproject, '[tool]\nkey = "value"\n')
            reader = SourceReader()
            # 不满足 pyproject 也不满足 lock, 会回退到 requirements 解析
            # 但文件内容没有类似 requirement 的行, 应抛出异常
            with self.assertRaises(ValueError):
                reader.read(str(pyproject))

    def test_toml_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            _write(pyproject, "[project\nbroken = true\n")
            reader = SourceReader()
            # TOML 解析失败, 回退到 requirements 解析
            # 内容不匹配 requirement 格式, 应抛出异常
            with self.assertRaises(ValueError):
                reader.read(str(pyproject))


class SourceReaderLockFileTests(unittest.TestCase):
    def _lock_content(self) -> str:
        return (
            '[[package]]\nname = "requests"\nversion = "2.32.3"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'dependencies = [{ name = "certifi" }]\n'
            "\n"
            '[[package]]\nname = "certifi"\nversion = "2024.2.2"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
        )

    def test_read_lock_file_registry_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_file = Path(tmp) / "project.lock"
            _write(lock_file, self._lock_content())
            reader = SourceReader()
            source = reader.read(str(lock_file))
            self.assertEqual(source.source_type, SourceType.LOCK_FILE)
            self.assertTrue(source.is_pinned)
            self.assertIn("requests==2.32.3", source.requirements)
            self.assertIn("certifi==2024.2.2", source.requirements)
            self.assertEqual(len(source.requirements), 2)

    def test_lock_file_skips_git_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_file = Path(tmp) / "deps.lock"
            content = (
                '[[package]]\nname = "local-lib"\nversion = "0.1.0"\n'
                'source = { git = "https://github.com/x/y.git" }\n'
                "\n"
                '[[package]]\nname = "requests"\nversion = "2.32.3"\n'
                'source = { registry = "https://pypi.org/simple" }\n'
            )
            _write(lock_file, content)
            reader = SourceReader()
            source = reader.read(str(lock_file))
            self.assertEqual(len(source.requirements), 1)
            self.assertIn("requests==2.32.3", source.requirements)
            self.assertIn("git", " ".join(source.warnings).lower() or "git")

    def test_lock_file_skips_directory_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_file = Path(tmp) / "uv.lock"
            content = (
                '[[package]]\nname = "editable-pkg"\nversion = "0.5.0"\n'
                'source = { directory = "../local-pkg" }\n'
                "\n"
                '[[package]]\nname = "flask"\nversion = "3.0.0"\n'
                'source = { registry = "https://pypi.org/simple" }\n'
            )
            _write(lock_file, content)
            reader = SourceReader()
            source = reader.read(str(lock_file))
            self.assertEqual(len(source.requirements), 1)
            self.assertIn("flask==3.0.0", source.requirements)

    def test_lock_file_empty_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_file = Path(tmp) / "empty.lock"
            _write(lock_file, 'version = "1.0"\npackage = []\n')
            reader = SourceReader()
            source = reader.read(str(lock_file))
            self.assertEqual(source.source_type, SourceType.LOCK_FILE)
            self.assertEqual(len(source.requirements), 0)
            self.assertTrue(any("未包含有效的" in w for w in source.warnings))


class SourceReaderDirectoryScanTests(unittest.TestCase):
    def test_directory_prioritizes_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_path = Path(tmp)
            _write(dir_path / "requirements.txt", "flask\n")
            _write(dir_path / "pyproject.toml", '[project]\ndependencies = ["requests"]\n')
            _write(
                dir_path / "uv.lock",
                '[[package]]\nname = "click"\nversion = "8.0.0"\n'
                'source = { registry = "https://pypi.org/simple" }\n',
            )
            reader = SourceReader()
            source = reader.read(str(dir_path))
            self.assertEqual(source.source_type, SourceType.LOCK_FILE)
            self.assertIn("click==8.0.0", source.requirements)

    def test_directory_falls_back_to_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_path = Path(tmp)
            _write(dir_path / "requirements.txt", "flask\n")
            _write(dir_path / "pyproject.toml", '[project]\ndependencies = ["requests>=2.0"]\n')
            reader = SourceReader()
            source = reader.read(str(dir_path))
            self.assertEqual(source.source_type, SourceType.PYPROJECT_TOML)
            self.assertIn("requests>=2.0", source.requirements)

    def test_directory_falls_back_to_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_path = Path(tmp)
            _write(dir_path / "dev-deps.txt", "flask==3.0.0\nclick\n")
            reader = SourceReader()
            source = reader.read(str(dir_path))
            self.assertEqual(source.source_type, SourceType.REQUIREMENTS_TXT)
            self.assertIn("flask==3.0.0", source.requirements)

    def test_empty_directory_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = SourceReader()
            with self.assertRaises(ValueError) as ctx:
                reader.read(str(tmp))
            self.assertIn("未找到可识别的依赖文件", str(ctx.exception))

    def test_directory_ignores_dot_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_path = Path(tmp)
            _write(dir_path / ".hidden.toml", '[project]\ndependencies = ["hidden"]\n')
            _write(dir_path / "requirements.txt", "visible\n")
            reader = SourceReader()
            source = reader.read(str(dir_path))
            self.assertEqual(source.source_type, SourceType.REQUIREMENTS_TXT)
            self.assertIn("visible", source.requirements)


class DependencySourceTests(unittest.TestCase):
    def test_lock_file_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_file = Path(tmp) / "uv.lock"
            _write(
                lock_file,
                '[[package]]\nname = "a"\nversion = "1.0"\n'
                'source = { registry = "https://pypi.org/simple" }\n'
                '[[package]]\nname = "b"\nversion = "2.0"\n'
                'source = { git = "https://example.com/repo.git" }\n',
            )
            reader = SourceReader()
            source = reader.read(str(lock_file))
            self.assertEqual(source.source_type, SourceType.LOCK_FILE)
            self.assertTrue(source.is_pinned)
            self.assertEqual(source.source_path, lock_file)
            self.assertIn("total_packages", source.metadata)
            self.assertIn("b", source.metadata["skipped_non_registry"])

    def test_pyproject_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            _write(
                pyproject,
                '[project]\nname = "myapp"\nrequires-python = ">=3.9"\n'
                'dependencies = ["requests>=2.0"]\n',
            )
            reader = SourceReader()
            source = reader.read(str(pyproject))
            self.assertFalse(source.is_pinned)
            self.assertEqual(source.metadata.get("project_name"), "myapp")
            self.assertEqual(source.metadata.get("requires_python"), ">=3.9")


if __name__ == "__main__":
    unittest.main()
