"""
Dependency resolution module using optional uv pip compile.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple


class DependencyResolver:
    """Resolve packages into pinned requirements for target Python/version/platform."""

    def __init__(
        self,
        python_version: str,
        platform: Optional[str] = None,
        pip_args: Optional[List[str]] = None,
        use_uv: bool = False,
        timeout: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        self.python_version = python_version
        self.platform = platform
        self.pip_args = pip_args or []
        self.use_uv = use_uv
        self.timeout = timeout if timeout and timeout > 0 else None
        self.verbose = verbose

    def resolve(self, packages: List[str]) -> Tuple[List[str], bool, Optional[str]]:
        """Resolve dependency list.

        Returns:
            pinned_reqs: resolved requirement lines (may be the original list on fallback)
            used_uv: whether uv was used
            error: optional error message when uv failed
        """
        if not packages:
            return [], False, None

        if self.use_uv and shutil.which("uv"):
            try:
                resolved = self._resolve_with_uv(packages)
                return resolved, True, None
            except subprocess.CalledProcessError as exc:  # uv failed
                msg = exc.stderr or exc.stdout or str(exc)
                if self.verbose and msg:
                    print(msg, file=sys.stderr)
                return packages, False, f"uv pip compile 失败，已回退原始列表: {msg.strip()}"
            except Exception as exc:  # pragma: no cover - safety net
                return packages, False, f"uv pip compile 异常，已回退原始列表: {exc}"

        if self.use_uv and not shutil.which("uv"):
            return packages, False, "未找到 uv，可选安装 uv 以提升跨版本依赖解析准确性"

        return packages, False, None

    def resolve_from_requirements_file(
        self,
        requirements_file: str
    ) -> Tuple[Optional[List[str]], bool, Optional[str]]:
        """
        从原始 requirements 文件解析依赖。

        Returns:
            resolved: uv 成功时返回解析后的 pinned 列表；否则为 None
            used_uv: 是否成功使用 uv
            error: uv 失败或不可用时的提示信息
        """
        if not self.use_uv:
            return None, False, None

        if not shutil.which("uv"):
            return None, False, "未找到 uv，可选安装 uv 以提升跨版本依赖解析准确性"

        try:
            resolved = self._resolve_with_uv_requirements_file(requirements_file)
            return resolved, True, None
        except subprocess.CalledProcessError as exc:
            msg = exc.stderr or exc.stdout or str(exc)
            if self.verbose and msg:
                print(msg, file=sys.stderr)
            return None, False, f"uv pip compile 失败，已回退原始 requirements: {msg.strip()}"
        except Exception as exc:  # pragma: no cover - safety net
            return None, False, f"uv pip compile 异常，已回退原始 requirements: {exc}"

    def _resolve_with_uv(self, packages: List[str]) -> List[str]:
        """Run uv pip compile on package list and return pinned requirements."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            in_file = tmp_path / "requirements.in"
            out_file = tmp_path / "requirements.txt"

            in_file.write_text("\n".join(packages), encoding="utf-8")
            return self._run_uv_compile(in_file, out_file)

    def _resolve_with_uv_requirements_file(self, requirements_file: str) -> List[str]:
        """Run uv pip compile on original requirements file and return pinned requirements."""
        if not requirements_file:
            raise ValueError("requirements_file is empty")
        input_file = Path(requirements_file)
        if not input_file.exists():
            raise FileNotFoundError(f"Requirements file not found: {requirements_file}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "requirements.txt"
            return self._run_uv_compile(input_file, out_file)

    def _run_uv_compile(self, input_file: Path, out_file: Path) -> List[str]:
        """Execute uv pip compile and parse pinned output."""
        cmd = [
            "uv",
            "pip",
            "compile",
            str(input_file),
            "--output-file",
            str(out_file),
            "--python-version",
            self.python_version,
        ]

        if self.platform and self.platform.lower() != "auto":
            platform = self._convert_platform(self.platform)
            cmd.extend(["--python-platform", platform])

        cmd.extend(self._convert_pip_args_for_uv(self.pip_args))

        if self.verbose:
            print("[uv]", " ".join(cmd))

        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        if not out_file.exists():
            raise RuntimeError("uv pip compile 未生成输出文件")

        lines = [line.strip() for line in out_file.read_text(encoding="utf-8").splitlines()]
        resolved = [line for line in lines if line and not line.startswith("#")]
        if not resolved:
            raise RuntimeError("uv pip compile 输出为空")

        return resolved

    @staticmethod
    def _convert_platform(platform: str) -> str:
        """
        Convert pip-style platform identifier to uv-style.

        pip: win_amd64, manylinux2014_x86_64, macosx_10_9_x86_64
        uv:  windows, linux, macos
        """
        platform_lower = platform.lower()

        if "win" in platform_lower:
            return "windows"
        elif "linux" in platform_lower or "manylinux" in platform_lower:
            return "linux"
        elif "macos" in platform_lower or "darwin" in platform_lower:
            return "macos"

        # Return original value (might be target triple)
        return platform

    @staticmethod
    def _convert_pip_args_for_uv(pip_args: List[str]) -> List[str]:
        """Convert pip-style args (index, extra-index, trusted-host) for uv."""
        uv_args: List[str] = []
        i = 0
        while i < len(pip_args):
            arg = pip_args[i]
            if arg == "--index-url" and i + 1 < len(pip_args):
                uv_args.extend(["--index-url", pip_args[i + 1]])
                i += 2
            elif arg == "--extra-index-url" and i + 1 < len(pip_args):
                uv_args.extend(["--extra-index-url", pip_args[i + 1]])
                i += 2
            elif arg == "--trusted-host":
                # uv 不需要 trusted-host，跳过 host 值
                i += 2
            else:
                i += 1
        return uv_args

