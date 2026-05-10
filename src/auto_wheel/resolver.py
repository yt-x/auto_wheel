"""
依赖解析模块（默认 uv，必要时回退 pip 语义）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .state_model import JobState, ResolutionStateSnapshot


class DependencyResolver:
    """将输入依赖解析为目标环境可用的 pinned requirements。"""

    _UNSAT_PATTERNS = (
        r"no solution found when resolving dependencies",
        r"unsatisfiable",
        r"has no wheels with a matching python abi tag",
        r"could not find a version that satisfies the requirement",
        r"no matching distribution found",
    )

    _DIRECT_PLATFORM_MAP: Dict[str, str] = {
        "win_amd64": "x86_64-pc-windows-msvc",
        "win32": "i686-pc-windows-msvc",
        "manylinux2014_x86_64": "x86_64-manylinux2014",
        "manylinux2014_aarch64": "aarch64-manylinux2014",
        "manylinux_2_17_x86_64": "x86_64-manylinux_2_17",
        "manylinux_2_17_aarch64": "aarch64-manylinux_2_17",
        "macosx_10_9_x86_64": "x86_64-apple-darwin",
        "macosx_11_0_arm64": "aarch64-apple-darwin",
    }

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
        normalized_platform = self._convert_platform(platform) if platform and platform.lower() != "auto" else None
        self.last_resolution_state = ResolutionStateSnapshot(
            job_state=JobState.CREATED,
            stage="resolver_init",
            resolver="none",
            reason="resolver initialized",
            target_platform=platform,
            normalized_platform=normalized_platform,
        )

    def get_last_resolution_state(self) -> Dict[str, str]:
        """获取最近一次解析状态快照。"""
        return self.last_resolution_state.to_dict()

    def _set_resolution_state(
        self,
        *,
        job_state: JobState,
        stage: str,
        resolver: str,
        failure_kind: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        normalized_platform = self._convert_platform(self.platform) if self.platform and self.platform.lower() != "auto" else None
        self.last_resolution_state = ResolutionStateSnapshot(
            job_state=job_state,
            stage=stage,
            resolver=resolver,
            failure_kind=failure_kind,
            reason=reason,
            target_platform=self.platform,
            normalized_platform=normalized_platform,
        )

    def resolve(self, packages: List[str]) -> Tuple[List[str], bool, Optional[str]]:
        """解析包列表。返回 (resolved_packages, used_uv, warning)。"""
        if not packages:
            self._set_resolution_state(
                job_state=JobState.PLANNING_READY,
                stage="resolver_empty_input",
                resolver="none",
                reason="no packages provided",
            )
            return [], False, None

        if self.use_uv and shutil.which("uv"):
            self._set_resolution_state(
                job_state=JobState.RESOLVING_UV,
                stage="uv_compile",
                resolver="uv",
                reason="starting uv pip compile",
            )
            try:
                resolved = self._resolve_with_uv(packages)
                self._set_resolution_state(
                    job_state=JobState.PLANNING_READY,
                    stage="uv_compile",
                    resolver="uv",
                    reason="uv compile succeeded",
                )
                return resolved, True, None
            except subprocess.CalledProcessError as exc:
                warning = self._build_uv_failure_message(exc, is_requirements_file=False)
                return packages, False, warning
            except Exception as exc:  # pragma: no cover - 兜底
                self._set_resolution_state(
                    job_state=JobState.RESOLVING_PIP_FALLBACK,
                    stage="uv_compile",
                    resolver="pip",
                    failure_kind="tool_error",
                    reason=str(exc),
                )
                return packages, False, f"uv pip compile 异常，已回退原始列表: {exc}"

        if self.use_uv and not shutil.which("uv"):
            reason = "未找到 uv，可选安装 uv 以提升跨版本依赖解析准确性"
            self._set_resolution_state(
                job_state=JobState.RESOLVING_PIP_FALLBACK,
                stage="uv_unavailable",
                resolver="pip",
                failure_kind="tool_error",
                reason=reason,
            )
            return packages, False, reason

        self._set_resolution_state(
            job_state=JobState.PLANNING_READY,
            stage="pip_direct",
            resolver="pip",
            reason="uv disabled by configuration",
        )
        return packages, False, None

    def resolve_from_requirements_file(
        self,
        requirements_file: str
    ) -> Tuple[Optional[List[str]], bool, Optional[str]]:
        """从 requirements 文件解析依赖。返回 (resolved_packages, used_uv, warning)。"""
        if not self.use_uv:
            self._set_resolution_state(
                job_state=JobState.PLANNING_READY,
                stage="pip_direct_requirements",
                resolver="pip",
                reason="uv disabled by configuration",
            )
            return None, False, None

        if not shutil.which("uv"):
            reason = "未找到 uv，可选安装 uv 以提升跨版本依赖解析准确性"
            self._set_resolution_state(
                job_state=JobState.RESOLVING_PIP_FALLBACK,
                stage="uv_unavailable",
                resolver="pip",
                failure_kind="tool_error",
                reason=reason,
            )
            return None, False, reason

        self._set_resolution_state(
            job_state=JobState.RESOLVING_UV,
            stage="uv_compile_requirements",
            resolver="uv",
            reason="starting uv compile with requirements file",
        )
        try:
            resolved = self._resolve_with_uv_requirements_file(requirements_file)
            self._set_resolution_state(
                job_state=JobState.PLANNING_READY,
                stage="uv_compile_requirements",
                resolver="uv",
                reason="uv compile succeeded",
            )
            return resolved, True, None
        except subprocess.CalledProcessError as exc:
            warning = self._build_uv_failure_message(exc, is_requirements_file=True)
            return None, False, warning
        except Exception as exc:  # pragma: no cover - 兜底
            self._set_resolution_state(
                job_state=JobState.RESOLVING_PIP_FALLBACK,
                stage="uv_compile_requirements",
                resolver="pip",
                failure_kind="tool_error",
                reason=str(exc),
            )
            return None, False, f"uv pip compile 异常，已回退原始 requirements: {exc}"

    def _build_uv_failure_message(self, exc: subprocess.CalledProcessError, is_requirements_file: bool) -> str:
        output = ((exc.stderr or "") + "\n" + (exc.stdout or "")).strip()
        failure_kind = self._classify_uv_failure(output)
        fallback_target = "原始 requirements" if is_requirements_file else "原始列表"
        if failure_kind == "unsatisfiable":
            message = f"uv 判定依赖在目标环境不可满足，已回退 {fallback_target}: {output}"
        else:
            message = f"uv pip compile 失败，已回退 {fallback_target}: {output}"

        self._set_resolution_state(
            job_state=JobState.RESOLVING_PIP_FALLBACK,
            stage="uv_compile",
            resolver="pip",
            failure_kind=failure_kind,
            reason=output or f"uv exited with code {exc.returncode}",
        )
        if self.verbose and output:
            print(output, file=sys.stderr)
        return message.strip()

    def _classify_uv_failure(self, output: str) -> str:
        """识别 uv 失败类型：unsatisfiable 或 tool_error。"""
        lowered = output.lower()
        for pattern in self._UNSAT_PATTERNS:
            if re.search(pattern, lowered):
                return "unsatisfiable"
        return "tool_error"

    def _resolve_with_uv(self, packages: List[str]) -> List[str]:
        """对 package 列表执行 uv pip compile。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            in_file = tmp_path / "requirements.in"
            out_file = tmp_path / "requirements.txt"

            in_file.write_text("\n".join(packages), encoding="utf-8")
            return self._run_uv_compile(in_file, out_file)

    def _resolve_with_uv_requirements_file(self, requirements_file: str) -> List[str]:
        """对 requirements 文件执行 uv pip compile。"""
        if not requirements_file:
            raise ValueError("requirements_file is empty")
        input_file = Path(requirements_file)
        if not input_file.exists():
            raise FileNotFoundError(f"Requirements file not found: {requirements_file}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "requirements.txt"
            return self._run_uv_compile(input_file, out_file)

    def _run_uv_compile(self, input_file: Path, out_file: Path) -> List[str]:
        """执行 uv pip compile 并读取解析结果。"""
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
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
        )

        if not out_file.exists():
            raise RuntimeError("uv pip compile 未生成输出文件")

        lines = [line.strip() for line in out_file.read_text(encoding="utf-8").splitlines()]
        resolved = [line for line in lines if line and not line.startswith("#")]
        if not resolved:
            raise RuntimeError("uv pip compile 输出为空")

        return resolved

    @classmethod
    def _convert_platform(cls, platform: str) -> str:
        """将 pip 平台标识转换为 uv 目标平台。"""
        platform_lower = platform.lower().strip()
        if platform_lower in cls._DIRECT_PLATFORM_MAP:
            return cls._DIRECT_PLATFORM_MAP[platform_lower]

        manylinux_match = re.match(r"manylinux(?:_|\d+_)?(\d+)?[_]?(\d+)?[_-](x86_64|aarch64)", platform_lower)
        if manylinux_match:
            arch = manylinux_match.group(3)
            if "2014" in platform_lower:
                return f"{arch}-manylinux2014"
            version_part = re.search(r"manylinux[_]?(\d+)_(\d+)", platform_lower)
            if version_part:
                return f"{arch}-manylinux_{version_part.group(1)}_{version_part.group(2)}"
            return f"{arch}-unknown-linux-gnu"

        if "win" in platform_lower:
            if "amd64" in platform_lower or "x86_64" in platform_lower:
                return "x86_64-pc-windows-msvc"
            if "win32" in platform_lower or "i686" in platform_lower or "x86" in platform_lower:
                return "i686-pc-windows-msvc"
            return "windows"

        if "linux" in platform_lower:
            if "aarch64" in platform_lower or "arm64" in platform_lower:
                return "aarch64-unknown-linux-gnu"
            if "x86_64" in platform_lower or "amd64" in platform_lower:
                return "x86_64-unknown-linux-gnu"
            return "linux"

        if "macosx" in platform_lower or "darwin" in platform_lower or "macos" in platform_lower:
            if "arm64" in platform_lower or "aarch64" in platform_lower:
                return "aarch64-apple-darwin"
            if "x86_64" in platform_lower or "amd64" in platform_lower:
                return "x86_64-apple-darwin"
            return "macos"

        return platform

    @staticmethod
    def _convert_pip_args_for_uv(pip_args: List[str]) -> List[str]:
        """将 pip 参数转换为 uv 兼容参数。"""
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
            elif arg == "--trusted-host" and i + 1 < len(pip_args):
                uv_args.extend(["--allow-insecure-host", pip_args[i + 1]])
                i += 2
            else:
                i += 1
        return uv_args

