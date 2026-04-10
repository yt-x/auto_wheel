"""
Package download module
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Deque, List, Optional, Dict, Any, Tuple
from urllib.parse import quote
from urllib.request import Request, urlopen

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


class WheelDownloader:
    """Download wheel packages using pip"""

    def __init__(
        self,
        python_version: str,
        output_dir: str = "./downloads",
        platform: Optional[str] = None,
        implementation: str = "cp",
        abi: Optional[str] = None,
        only_binary: str = ":all:",
        verbose: bool = False,
        config_pip_args: Optional[List[str]] = None,
        use_uv_resolver: bool = True,
        max_attempts: int = 3,
        retry_delay: float = 3.0,
        command_timeout: Optional[int] = None
    ) -> None:
        """
        Initialize downloader

        Args:
            python_version: Target Python version (e.g., "3.9")
            output_dir: Directory to save downloaded wheels
            platform: Target platform (e.g., "win_amd64", "manylinux2014_x86_64")
            implementation: Python implementation (default: "cp" for CPython)
            abi: Python ABI tag
            only_binary: Only download binary wheels (default: ":all:")
            verbose: Enable verbose output
            config_pip_args: Additional pip arguments from config
            use_uv_resolver: Whether to allow uv in fallback dependency resolution
            max_attempts: Maximum times to invoke pip download when failures occur
            retry_delay: Seconds to wait between attempts (linear backoff)
            command_timeout: Overall timeout (seconds) for each pip invocation
        """
        self.python_version = python_version
        self.output_dir = Path(output_dir)
        self.platform = platform
        self.implementation = implementation
        self.abi = abi or self._get_abi_tag()
        self.only_binary = only_binary
        self.verbose = verbose
        self.config_pip_args = config_pip_args or []
        self.use_uv_resolver = bool(use_uv_resolver)
        self.max_attempts = max(1, max_attempts)
        self.retry_delay = max(0.0, retry_delay)
        self.command_timeout = command_timeout if command_timeout and command_timeout > 0 else None
        self.source_fallback_report_path = self.output_dir / "source-fallback-report.json"

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_abi_tag(self) -> str:
        """Generate ABI tag from Python version"""
        # For CPython, ABI tag is like "cp39" for Python 3.9
        version_parts = self.python_version.split(".")
        major, minor = version_parts[0], version_parts[1]
        return f"{self.implementation}{major}{minor}"

    def _build_pip_command(self, packages: List[str], dry_run: bool = False) -> List[str]:
        """
        Build pip download command

        Args:
            packages: List of package names or requirements
            dry_run: If True, add --dry-run flag

        Returns:
            Complete pip command as list
        """
        cmd = [
            sys.executable, "-m", "pip", "download",
            "--dest", str(self.output_dir),
        ]

        # Add Python version
        cmd.extend(["--python-version", self.python_version])

        # Add platform if specified
        if self.platform and self.platform.lower() != "auto":
            cmd.extend(["--platform", self.platform])

        # Add implementation
        cmd.extend(["--implementation", self.implementation])

        # Add ABI
        cmd.extend(["--abi", self.abi])

        # Only binary
        if self.only_binary:
            cmd.extend(["--only-binary", self.only_binary])

        # Config pip arguments (index URLs, trusted hosts, etc.)
        if self.config_pip_args:
            cmd.extend(self.config_pip_args)

        # Verbose
        if self.verbose:
            cmd.append("-v")

        # Packages
        cmd.extend(packages)

        return cmd

    @staticmethod
    def _remove_only_binary(cmd: List[str]) -> List[str]:
        """Return a copy of command with --only-binary removed."""
        filtered: List[str] = []
        idx = 0
        while idx < len(cmd):
            token = cmd[idx]
            if token == "--only-binary":
                idx += 2
                continue
            filtered.append(token)
            idx += 1
        return filtered

    @staticmethod
    def _remove_target_constraints(cmd: List[str], keep_python_version: bool = False) -> List[str]:
        """Return a copy of command without target platform constraints.

        Args:
            cmd: 原始 pip 命令
            keep_python_version: 是否保留 --python-version。
                注意：pip 限制：使用 --python-version 时必须同时用 --no-deps 或 --only-binary=:all:
                因此只有当 source_fallback_no_deps=True 时才应该保留。
        """
        filtered: List[str] = []
        if keep_python_version:
            # 只移除平台相关约束，保留 --python-version
            constraint_flags = {"--platform", "--implementation", "--abi"}
        else:
            # 移除所有约束（包括 --python-version）
            constraint_flags = {"--python-version", "--platform", "--implementation", "--abi"}
        idx = 0
        while idx < len(cmd):
            token = cmd[idx]
            if token in constraint_flags:
                idx += 2
                continue
            filtered.append(token)
            idx += 1
        return filtered

    def _build_source_fallback_command(self, cmd: List[str], source_fallback_no_deps: bool) -> List[str]:
        """Build fallback command that allows sdist download under pip constraints.

        策略：
        - source_fallback_no_deps=True（uv 预解析）：保留 --python-version，添加 --no-deps
        - source_fallback_no_deps=False（原始列表）：移除所有约束，使用当前环境 Python
        """
        without_only_binary = self._remove_only_binary(cmd)
        fallback_cmd = self._remove_target_constraints(
            without_only_binary,
            keep_python_version=source_fallback_no_deps
        )
        if source_fallback_no_deps and "--no-deps" not in fallback_cmd:
            fallback_cmd.append("--no-deps")
        return fallback_cmd

    @staticmethod
    def _is_uv_available() -> bool:
        """Check whether uv executable is available."""
        return shutil.which("uv") is not None

    @staticmethod
    def _parse_requirement_name(requirement: str) -> Optional[str]:
        """Extract canonical package name from requirement string."""
        try:
            parsed = Requirement(requirement)
            return canonicalize_name(parsed.name)
        except Exception:
            match = re.match(r"^\s*([A-Za-z0-9_.-]+)", requirement or "")
            if not match:
                return None
            return canonicalize_name(match.group(1))

    @staticmethod
    def _convert_pip_args_for_uv(pip_args: List[str]) -> List[str]:
        """Convert pip-style args to uv compile args."""
        uv_args: List[str] = []
        idx = 0
        while idx < len(pip_args):
            arg = pip_args[idx]
            if arg == "--index-url" and idx + 1 < len(pip_args):
                uv_args.extend(["--index-url", pip_args[idx + 1]])
                idx += 2
                continue
            if arg == "--extra-index-url" and idx + 1 < len(pip_args):
                uv_args.extend(["--extra-index-url", pip_args[idx + 1]])
                idx += 2
                continue
            if arg == "--trusted-host":
                idx += 2
                continue
            idx += 1
        return uv_args

    @staticmethod
    def _convert_platform_for_uv(platform: str) -> str:
        """Convert pip-style platform identifier to uv-style."""
        platform_lower = platform.lower()
        if "win" in platform_lower:
            return "windows"
        if "linux" in platform_lower or "manylinux" in platform_lower:
            return "linux"
        if "macos" in platform_lower or "darwin" in platform_lower:
            return "macos"
        return platform

    def _build_marker_environment(self) -> Dict[str, str]:
        """Build marker evaluation environment for target Python/platform."""
        env = default_environment()
        env["python_version"] = self.python_version
        env["python_full_version"] = f"{self.python_version}.0"

        platform_lower = (self.platform or "").lower()
        if "win" in platform_lower:
            env["sys_platform"] = "win32"
            env["platform_system"] = "Windows"
        elif "linux" in platform_lower or "manylinux" in platform_lower:
            env["sys_platform"] = "linux"
            env["platform_system"] = "Linux"
        elif "macos" in platform_lower or "darwin" in platform_lower:
            env["sys_platform"] = "darwin"
            env["platform_system"] = "Darwin"
        return env

    def _normalize_dependencies(self, requirements: List[str], current_package: str) -> List[str]:
        """Normalize and deduplicate requirement strings."""
        normalized: List[str] = []
        seen: set[str] = set()
        current_name = self._parse_requirement_name(current_package) if current_package else None
        marker_env = self._build_marker_environment()

        for raw_req in requirements:
            if not raw_req:
                continue
            try:
                parsed = Requirement(raw_req)
                if parsed.marker and not parsed.marker.evaluate(marker_env):
                    continue
                dep_name = canonicalize_name(parsed.name)
                if dep_name == current_name:
                    continue
                specifier = str(parsed.specifier)
                requirement_str = parsed.name + specifier if specifier else parsed.name
            except Exception:
                dep_name = self._parse_requirement_name(raw_req)
                if not dep_name or dep_name == current_name:
                    continue
                requirement_str = dep_name

            if dep_name in seen:
                continue
            seen.add(dep_name)
            normalized.append(requirement_str)

        return normalized

    def _extract_requested_requirements(self, cmd: List[str]) -> List[str]:
        """Extract requested requirement items from a pip download command."""
        requirements: List[str] = []
        options_with_value = {
            "--dest", "--python-version", "--platform", "--implementation", "--abi",
            "--only-binary", "--no-binary", "--index-url", "--extra-index-url",
            "--trusted-host", "--timeout", "--retries",
        }
        idx = 0
        while idx < len(cmd):
            token = cmd[idx]
            if token in {"-r", "--requirement"}:
                if idx + 1 < len(cmd):
                    req_path = Path(cmd[idx + 1])
                    requirements.extend(self._read_requirements_file(req_path))
                idx += 2
                continue
            if token in options_with_value:
                idx += 2
                continue
            if token.startswith("-"):
                idx += 1
                continue
            if token == sys.executable:
                idx += 1
                continue
            if token in {"-m", "pip", "download"}:
                idx += 1
                continue
            requirements.append(token)
            idx += 1
        return requirements

    @staticmethod
    def _read_requirements_file(req_path: Path) -> List[str]:
        """Read a requirements file and return plain requirement lines."""
        if not req_path.exists():
            return []
        requirements: List[str] = []
        for line in req_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("-r ") or line.startswith("--requirement "):
                nested = line.split(maxsplit=1)[1].strip()
                nested_path = (req_path.parent / nested).resolve()
                requirements.extend(WheelDownloader._read_requirements_file(nested_path))
                continue
            requirements.append(line)
        return requirements

    def _build_requirement_lookup(self, requirements: List[str]) -> Dict[str, str]:
        """Build canonical-name -> requirement mapping."""
        lookup: Dict[str, str] = {}
        for item in requirements:
            dep_name = self._parse_requirement_name(item)
            if dep_name and dep_name not in lookup:
                lookup[dep_name] = item
        return lookup

    def _build_requirement_lookup_from_cmd(self, cmd: List[str]) -> Dict[str, str]:
        """Build lookup map from original pip command input."""
        requested = self._extract_requested_requirements(cmd)
        return self._build_requirement_lookup(requested)

    def _build_probe_wheel_command(self, requirement: str, destination: Path) -> List[str]:
        """Build probe command for checking whether a requirement has wheel."""
        cmd = [
            sys.executable, "-m", "pip", "download",
            "--dest", str(destination),
            "--no-deps",
            "--only-binary", ":all:",
            "--python-version", self.python_version,
        ]
        if self.platform and self.platform.lower() != "auto":
            cmd.extend(["--platform", self.platform])
        cmd.extend(["--implementation", self.implementation])
        cmd.extend(["--abi", self.abi])
        if self.config_pip_args:
            cmd.extend(self.config_pip_args)
        if self.verbose:
            cmd.append("-v")
        cmd.append(requirement)
        return cmd

    def _probe_wheel_availability(self, requirement: str, is_root_requirement: bool) -> Dict[str, Any]:
        """Probe whether wheel is available for requirement under target constraints."""
        dep_name = self._parse_requirement_name(requirement) or requirement
        with tempfile.TemporaryDirectory() as tmp_dir:
            probe_cmd = self._build_probe_wheel_command(requirement, Path(tmp_dir))
            result = self._run_with_retries(probe_cmd, stage=f"probe_wheel:{dep_name}")

        if result.get("success"):
            return {
                "status": "wheel_available",
                "reason": "单包 wheel 探测成功",
                "is_root_requirement": is_root_requirement,
            }

        errors = result.get("errors", [])
        no_wheel_reason = self._detect_no_wheel_reason(errors)
        if no_wheel_reason:
            return {
                "status": "no_wheel",
                "reason": no_wheel_reason,
                "is_root_requirement": is_root_requirement,
            }

        return {
            "status": "inconclusive",
            "reason": result.get("error", "单包 wheel 探测失败，但非无 wheel 场景"),
            "is_root_requirement": is_root_requirement,
        }

    def _build_wheel_no_deps_command(self, requirement: str) -> List[str]:
        """Build command for downloading wheel of one requirement without dependency resolution."""
        cmd = [
            sys.executable, "-m", "pip", "download",
            "--dest", str(self.output_dir),
            "--no-deps",
            "--python-version", self.python_version,
        ]
        if self.platform and self.platform.lower() != "auto":
            cmd.extend(["--platform", self.platform])
        cmd.extend(["--implementation", self.implementation])
        cmd.extend(["--abi", self.abi])
        if self.only_binary:
            cmd.extend(["--only-binary", self.only_binary])
        if self.config_pip_args:
            cmd.extend(self.config_pip_args)
        if self.verbose:
            cmd.append("-v")
        cmd.append(requirement)
        return cmd

    def _download_root_wheels_no_deps(
        self,
        root_requirements: List[str],
        probe_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Download root wheels without deps for requirements proven wheel-available."""
        downloaded: List[str] = []
        failed: List[str] = []
        warnings: List[str] = []
        errors: List[Dict[str, Any]] = []

        for requirement in root_requirements:
            root_key = self._parse_requirement_name(requirement)
            if not root_key:
                continue
            probe = probe_results.get(root_key) or {}
            if probe.get("probe_result") != "wheel_available":
                continue

            result = self._run_with_retries(
                self._build_wheel_no_deps_command(requirement),
                stage=f"root_wheel:{root_key}",
            )
            if result.get("success"):
                downloaded.append(requirement)
                continue

            failed.append(requirement)
            errors.extend(result.get("errors", []))
            no_wheel_reason = self._detect_no_wheel_reason(result.get("errors", []))
            if no_wheel_reason:
                warnings.append(f"{requirement} 根包 wheel(no-deps) 下载失败：{no_wheel_reason}")
            else:
                warnings.append(f"{requirement} 根包 wheel(no-deps) 下载失败：{result.get('error', 'unknown')}")

        return {
            "downloaded": downloaded,
            "failed": failed,
            "warnings": warnings,
            "errors": errors,
        }

    def _download_dependency_wheels_no_deps(
        self,
        dependency_requirements: List[str],
        probe_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Download dependency wheels proven as wheel-available with normal dependency resolution."""
        downloaded: List[str] = []
        failed: List[str] = []
        warnings: List[str] = []
        errors: List[Dict[str, Any]] = []
        promote_to_source: List[str] = []

        for requirement in dependency_requirements:
            dep_key = self._parse_requirement_name(requirement)
            if not dep_key:
                continue
            probe = probe_results.get(dep_key) or {}
            if probe.get("probe_result") != "wheel_available":
                continue

            result = self._run_with_retries(
                self._build_pip_command([requirement], dry_run=False),
                stage=f"deps_wheel_preload:{dep_key}",
            )
            if result.get("success"):
                downloaded.append(requirement)
                continue

            failed.append(requirement)
            errors.extend(result.get("errors", []))
            no_wheel_reason = self._detect_no_wheel_reason(result.get("errors", []))
            if no_wheel_reason:
                promote_to_source.append(requirement)
                probe_results[dep_key] = {
                    "requirement": requirement,
                    "probe_result": "no_wheel",
                    "probe_reason": no_wheel_reason,
                    "is_root_requirement": False,
                }
                warnings.append(f"{requirement} 预下载 wheel 失败且无 wheel，转源码候选")
            else:
                warnings.append(f"{requirement} 预下载 wheel 失败：{result.get('error', 'unknown')}")

        return {
            "downloaded": downloaded,
            "failed": failed,
            "warnings": warnings,
            "errors": errors,
            "promote_to_source": promote_to_source,
        }

    def _discover_source_candidates_from_roots(
        self,
        root_requirements: List[str],
        probe_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Discover source candidates by scanning root requirements and their dependencies."""
        source_candidates: List[str] = []
        wheel_requirements: List[str] = []
        warnings: List[str] = []

        for root_requirement in root_requirements:
            root_key = self._parse_requirement_name(root_requirement)
            if not root_key:
                continue

            if root_key not in probe_results:
                root_probe = self._probe_wheel_availability(root_requirement, is_root_requirement=True)
                probe_results[root_key] = {
                    "requirement": root_requirement,
                    "probe_result": root_probe.get("status"),
                    "probe_reason": root_probe.get("reason"),
                    "is_root_requirement": True,
                }
                if root_probe.get("status") == "no_wheel":
                    source_candidates.append(root_requirement)
                elif root_probe.get("status") == "inconclusive":
                    warnings.append(f"{root_requirement} 根包探测不确定，暂不转源码")

            deps_info = self._resolve_source_dependencies(root_requirement)
            for dep_warning in deps_info.get("warnings", []):
                warnings.append(f"{root_requirement}: {dep_warning}")

            for dep_requirement in deps_info.get("dependencies", []):
                dep_key = self._parse_requirement_name(dep_requirement)
                if not dep_key:
                    continue
                if dep_key in probe_results:
                    if probe_results[dep_key].get("probe_result") == "no_wheel":
                        source_candidates.append(dep_requirement)
                    elif probe_results[dep_key].get("probe_result") == "wheel_available":
                        wheel_requirements.append(dep_requirement)
                    continue

                dep_probe = self._probe_wheel_availability(dep_requirement, is_root_requirement=False)
                probe_results[dep_key] = {
                    "requirement": dep_requirement,
                    "probe_result": dep_probe.get("status"),
                    "probe_reason": dep_probe.get("reason"),
                    "is_root_requirement": False,
                }
                if dep_probe.get("status") == "no_wheel":
                    source_candidates.append(dep_requirement)
                elif dep_probe.get("status") == "wheel_available":
                    wheel_requirements.append(dep_requirement)
                elif dep_probe.get("status") == "inconclusive":
                    warnings.append(f"{dep_requirement} 依赖探测不确定，暂不转源码")

        deduped = list(dict.fromkeys(source_candidates))
        deduped_wheels = list(dict.fromkeys(wheel_requirements))
        return {
            "source_candidates": deduped,
            "wheel_requirements": deduped_wheels,
            "warnings": warnings,
            "probe_results": probe_results,
        }

    @staticmethod
    def _extract_exact_version(requirement: str) -> Optional[str]:
        """Extract exact version from requirement like name==1.2.3."""
        try:
            parsed = Requirement(requirement)
            for spec in parsed.specifier:
                if spec.operator == "==" and "*" not in spec.version:
                    return spec.version
        except Exception:
            return None
        return None

    def _resolve_dependencies_with_uv(self, requirement: str) -> Tuple[List[str], Optional[str]]:
        """Resolve dependency candidates by uv compile."""
        if not self._is_uv_available():
            return [], "uv 不可用"

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            in_file = tmp_path / "requirements.in"
            out_file = tmp_path / "requirements.txt"
            in_file.write_text(requirement, encoding="utf-8")

            cmd = [
                "uv",
                "pip",
                "compile",
                str(in_file),
                "--output-file",
                str(out_file),
                "--python-version",
                self.python_version,
            ]
            if self.platform and self.platform.lower() != "auto":
                cmd.extend(["--python-platform", self._convert_platform_for_uv(self.platform)])
            cmd.extend(self._convert_pip_args_for_uv(self.config_pip_args))

            run_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
            )
            if run_result.returncode != 0:
                detail = (run_result.stderr or run_result.stdout or "").strip()
                return [], f"uv 解析失败: {detail or 'unknown'}"

            if not out_file.exists():
                return [], "uv 未生成解析结果"

            lines = [
                line.split("#", 1)[0].strip()
                for line in out_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            base_name = self._parse_requirement_name(requirement)
            resolved = [
                line for line in lines
                if self._parse_requirement_name(line) != base_name
            ]
            return resolved, None

    def _resolve_dependencies_from_pypi(self, requirement: str) -> Tuple[List[str], Optional[str]]:
        """Resolve dependency candidates from PyPI metadata requires_dist."""
        dep_name = self._parse_requirement_name(requirement)
        if not dep_name:
            return [], "无法解析包名（PyPI 元数据）"

        exact_version = self._extract_exact_version(requirement)
        urls = []
        if exact_version:
            urls.append(f"https://pypi.org/pypi/{quote(dep_name)}/{quote(exact_version)}/json")
        urls.append(f"https://pypi.org/pypi/{quote(dep_name)}/json")

        last_error = "PyPI 元数据不可用"
        for url in urls:
            try:
                req = Request(url, headers={"Accept": "application/json", "User-Agent": "auto-wheel/2.0"})
                with urlopen(req, timeout=min(self.command_timeout or 30, 30)) as response:
                    data = json.loads(response.read().decode("utf-8"))
                info = data.get("info", {})
                requires_dist = info.get("requires_dist") or []
                return requires_dist, None
            except Exception as exc:  # pragma: no cover - 网络失败场景
                last_error = f"{type(exc).__name__}: {exc}"
        return [], f"PyPI 元数据读取失败: {last_error}"

    def _resolve_dependencies_with_pip_report(self, requirement: str) -> Tuple[List[str], Optional[str]]:
        """Resolve dependency candidates by pip --dry-run report."""
        cmd = [
            sys.executable, "-m", "pip", "install",
            "--dry-run", "--ignore-installed",
            "--report", "-",
            requirement,
        ]
        if self.config_pip_args:
            cmd.extend(self.config_pip_args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.command_timeout or 120,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return [], f"pip report 解析失败: {detail or 'unknown'}"

        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            return [], "pip report 输出非 JSON"

        target_name = self._parse_requirement_name(requirement)
        requires_dist: List[str] = []
        for item in report.get("install", []):
            metadata = item.get("metadata") or {}
            name = canonicalize_name(str(metadata.get("name") or "")) if metadata.get("name") else None
            if target_name and name == target_name:
                requires_dist = metadata.get("requires_dist") or []
                break
        if not requires_dist:
            for item in report.get("install", []):
                metadata = item.get("metadata") or {}
                requires_dist.extend(metadata.get("requires_dist") or [])
        return requires_dist, None

    def _resolve_source_dependencies(self, requirement: str) -> Dict[str, Any]:
        """Resolve dependencies with conservative order and return structured result."""
        warnings: List[str] = []

        pypi_deps, pypi_error = self._resolve_dependencies_from_pypi(requirement)
        if pypi_error:
            warnings.append(pypi_error)
        else:
            return {
                "dependencies": self._normalize_dependencies(pypi_deps, requirement),
                "source": "pypi",
                "warnings": warnings,
            }

        pip_deps, pip_error = self._resolve_dependencies_with_pip_report(requirement)
        if pip_error:
            warnings.append(pip_error)
        else:
            return {
                "dependencies": self._normalize_dependencies(pip_deps, requirement),
                "source": "pip",
                "warnings": warnings,
            }

        if self.use_uv_resolver:
            uv_deps, uv_error = self._resolve_dependencies_with_uv(requirement)
            if uv_error:
                warnings.append(uv_error)
            else:
                return {
                    "dependencies": self._normalize_dependencies(uv_deps, requirement),
                    "source": "uv",
                    "warnings": warnings,
                }
        else:
            warnings.append("use_uv_resolver=false，已跳过 uv 解析")

        return {
            "dependencies": [],
            "source": "none",
            "warnings": warnings,
        }

    def _write_source_fallback_report(self, report: Dict[str, Any]) -> None:
        """Persist source fallback report for guide generation and auditing."""
        self.source_fallback_report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _clear_source_fallback_report(self) -> None:
        """Remove stale source fallback report before a new run."""
        try:
            self.source_fallback_report_path.unlink(missing_ok=True)
        except Exception:
            if self.verbose:
                print("[source_fallback] 清理旧报告失败", file=sys.stderr)

    def _download_source_package_separate(
        self,
        package: str,
        source_dir: Path
    ) -> Dict[str, Any]:
        """单独下载单个源码包（无平台/Python版本约束，不解析依赖）。

        用于分离策略：当某个包只有源码可用时，单独下载它到 sources/ 目录。

        Returns:
            Dict with success status and metadata
        """
        # 确保 sources 目录存在
        source_dir.mkdir(parents=True, exist_ok=True)

        # 构建无约束的命令：移除 --only-binary, --python-version, --platform 等
        cmd = [
            sys.executable, "-m", "pip", "download",
            "--dest", str(source_dir),
            "--no-deps",  # 不下载依赖
            "--no-binary", ":all:",  # 强制使用源码
        ]

        # 添加配置中的 pip 参数（如镜像源）
        if self.config_pip_args:
            cmd.extend(self.config_pip_args)

        if self.verbose:
            cmd.append("-v")

        cmd.append(package)

        if self.verbose:
            print(f"[source_separate] Downloading source for: {package}")
            print(f"[source_separate] Command: {' '.join(cmd)}")

        result = self._run_with_retries(cmd, stage=f"source_separate:{package}")

        if result["success"]:
            return {
                "success": True,
                "package": package,
                "source_dir": str(source_dir),
                "output": result.get("output", ""),
                "attempts": result.get("attempts", 1),
            }
        else:
            return {
                "success": False,
                "package": package,
                "error": result.get("error", "Unknown error"),
                "errors": result.get("errors", []),
            }

    @staticmethod
    def _queue_requirement(
        queue: Deque[str],
        queued_keys: set[str],
        requirement: str,
    ) -> None:
        """Append requirement to queue once."""
        queue_key = WheelDownloader._parse_requirement_name(requirement) or requirement.strip().lower()
        if not queue_key or queue_key in queued_keys:
            return
        queued_keys.add(queue_key)
        queue.append(requirement)

    def _execute_separate_strategy(
        self,
        source_candidates: List[str],
        wheel_stage_result: Dict[str, Any],
        fallback_reason: str,
        probe_results: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """执行分离策略：单独处理源码包和其依赖的 wheel。

        核心逻辑：
        1. 对只有源码的包：单独用 --no-deps 下载到 sources/（无 Python 版本约束）
        2. 对这些包的依赖：使用正常 wheel 流程下载（有 Python 版本约束）

        这样可以确保依赖的 wheel 是正确的 Python 版本（如 cp39），
        而不是当前环境的版本（如 cp313）。

        Returns:
            Dict with combined results
        """
        source_dir = self.output_dir / "sources"
        all_errors = list(wheel_stage_result.get("errors", []))
        source_packages_downloaded: List[str] = []
        source_packages_failed: List[Tuple[str, str]] = []
        deps_wheel_downloaded: List[str] = []
        source_processed: set[str] = set()
        wheel_downloaded: set[str] = set()

        queue: Deque[str] = deque()
        queued_keys: set[str] = set()
        for candidate in source_candidates:
            self._queue_requirement(queue, queued_keys, candidate)

        report: Dict[str, Any] = {
            "strategy": "separate_recursive",
            "target_python_version": self.python_version,
            "fallback_reason": fallback_reason,
            "source_packages": {},
            "warnings": [],
            "errors_count": 0,
            "candidate_probes": probe_results or {},
        }

        print(f"\n[separate_strategy] 使用分离递归策略处理源码包，初始候选 {len(queue)} 个")
        while queue:
            source_requirement = queue.popleft()
            source_name = self._parse_requirement_name(source_requirement) or source_requirement
            source_key = canonicalize_name(source_name) if source_name else source_requirement
            source_processed.add(source_key)

            pkg_report: Dict[str, Any] = {
                "requirement": source_requirement,
                "dependency_source": "none",
                "dependencies": [],
                "source_dependencies": [],
                "wheel_dependencies": [],
                "failed_wheel_dependencies": [],
                "warnings": [],
                "source_downloaded": False,
                "probe_result": (report.get("candidate_probes", {}).get(source_key) or {}).get("probe_result"),
                "probe_reason": (report.get("candidate_probes", {}).get(source_key) or {}).get("probe_reason"),
                "is_root_requirement": (report.get("candidate_probes", {}).get(source_key) or {}).get("is_root_requirement"),
            }

            print(f"\n[separate_strategy] 处理源码包: {source_requirement}")
            source_result = self._download_source_package_separate(source_requirement, source_dir)
            if not source_result["success"]:
                error_msg = source_result.get("error", "Unknown")
                source_packages_failed.append((source_requirement, error_msg))
                all_errors.extend(source_result.get("errors", []))
                pkg_report["warnings"].append(f"源码包下载失败: {error_msg}")
                report["source_packages"][source_key] = pkg_report
                print(f"  [FAIL] 源码包下载失败: {error_msg}")
                continue

            source_packages_downloaded.append(source_requirement)
            pkg_report["source_downloaded"] = True

            deps_info = self._resolve_source_dependencies(source_requirement)
            dependencies = deps_info.get("dependencies", [])
            pkg_report["dependency_source"] = deps_info.get("source", "none")
            pkg_report["dependencies"] = dependencies
            pkg_report["warnings"].extend(deps_info.get("warnings", []))

            if deps_info.get("warnings"):
                for warning in deps_info["warnings"]:
                    report["warnings"].append(f"{source_requirement}: {warning}")

            if dependencies:
                print(f"  [INFO] 解析到依赖 {len(dependencies)} 个（来源: {pkg_report['dependency_source']}）")
            else:
                print(f"  [INFO] 未解析到依赖（来源: {pkg_report['dependency_source']}）")

            for dep_requirement in dependencies:
                dep_key = self._parse_requirement_name(dep_requirement)
                if dep_key and dep_key in source_processed:
                    pkg_report["source_dependencies"].append(dep_requirement)
                    continue
                if dep_key and dep_key in wheel_downloaded:
                    pkg_report["wheel_dependencies"].append(dep_requirement)
                    continue

                stage_name = f"deps_wheel:{source_key}:{dep_key or dep_requirement}"
                dep_result = self._run_with_retries(
                    self._build_pip_command([dep_requirement], dry_run=False),
                    stage=stage_name,
                )
                if dep_result.get("success"):
                    if dep_key:
                        wheel_downloaded.add(dep_key)
                    deps_wheel_downloaded.append(dep_requirement)
                    pkg_report["wheel_dependencies"].append(dep_requirement)
                    continue

                dep_errors = dep_result.get("errors", [])
                all_errors.extend(dep_errors)
                no_wheel_reason = self._detect_no_wheel_reason(dep_errors)
                if no_wheel_reason:
                    probe_info = self._probe_wheel_availability(
                        dep_requirement,
                        is_root_requirement=False,
                    )
                    dep_key_for_probe = self._parse_requirement_name(dep_requirement) or dep_requirement
                    report["candidate_probes"][dep_key_for_probe] = {
                        "requirement": dep_requirement,
                        "probe_result": probe_info.get("status"),
                        "probe_reason": probe_info.get("reason"),
                        "is_root_requirement": False,
                    }
                    if probe_info.get("status") == "no_wheel":
                        pkg_report["source_dependencies"].append(dep_requirement)
                        self._queue_requirement(queue, queued_keys, dep_requirement)
                        report["warnings"].append(
                            f"{source_requirement} 的依赖 {dep_requirement} 无 wheel，已加入源码队列"
                        )
                    elif probe_info.get("status") == "wheel_available":
                        pkg_report["wheel_dependencies"].append(dep_requirement)
                        report["warnings"].append(
                            f"{source_requirement} 的依赖 {dep_requirement} 初次失败，但单包探测有 wheel，已保留 wheel 路径"
                        )
                    else:
                        pkg_report["failed_wheel_dependencies"].append(dep_requirement)
                        report["warnings"].append(
                            f"{source_requirement} 的依赖 {dep_requirement} 探测不确定，未自动转源码"
                        )
                else:
                    pkg_report["failed_wheel_dependencies"].append(dep_requirement)
                    warn_msg = dep_result.get("error", "依赖 wheel 下载失败")
                    pkg_report["warnings"].append(f"{dep_requirement}: {warn_msg}")
                    report["warnings"].append(f"{source_requirement} 的依赖 {dep_requirement} 下载失败: {warn_msg}")

            report["source_packages"][source_key] = pkg_report

        report["errors_count"] = len(all_errors)
        report["source_package_count"] = len(source_packages_downloaded)
        report["failed_source_package_count"] = len(source_packages_failed)
        report["wheel_dependency_count"] = len(set(deps_wheel_downloaded))
        self._write_source_fallback_report(report)

        if not source_packages_downloaded:
            return {
                "success": False,
                "error": f"无法下载任何源码包: {source_packages_failed}",
                "errors": all_errors,
                "downloaded_to": str(self.output_dir),
                "used_source_fallback": True,
                "fallback_reason": fallback_reason,
                "source_fallback_report": report,
            }

        summary_lines = [
            "分离递归策略处理完成：",
            f"  - 源码包已下载 ({len(source_packages_downloaded)}): {', '.join(source_packages_downloaded)}",
            f"  - 依赖 wheel 已处理 ({len(set(deps_wheel_downloaded))} 个唯一依赖)",
            f"  - 告警数量: {len(report['warnings'])}",
        ]
        if source_packages_failed:
            summary_lines.append(
                f"  - 源码包失败 ({len(source_packages_failed)}): "
                + ", ".join(pkg for pkg, _ in source_packages_failed)
            )
        summary_lines.append(f"\n注意：依赖的 wheel 使用 Python {self.python_version} 约束下载")
        summary_lines.append("源码包需要在目标环境按 SOURCE_INSTALL_GUIDE.md 处理后再安装离线依赖")
        summary = "\n".join(summary_lines)
        print(f"\n[separate_strategy] {summary}")

        return {
            "success": True,
            "output": summary,
            "downloaded_to": str(self.output_dir),
            "attempts": 1,
            "errors": all_errors,
            "used_source_fallback": True,
            "fallback_reason": fallback_reason,
            "source_packages": source_packages_downloaded,
            "source_packages_failed": [p for p, _ in source_packages_failed],
            "source_fallback_report": report,
        }

    @staticmethod
    def _extract_stage_hint(errors: List[Dict[str, Any]]) -> Optional[str]:
        """Extract a concise hint from stage errors when available."""
        if not errors:
            return None

        for err in reversed(errors):
            stderr = (err.get("stderr") or "").strip()
            stdout = (err.get("stdout") or "").strip()
            if stderr:
                return stderr
            if stdout:
                return stdout
        return None

    @staticmethod
    def _detect_no_wheel_reason(errors: List[Dict[str, Any]]) -> Optional[str]:
        """Return reason when failures indicate no wheel/no matching distribution."""
        if not errors:
            return None

        patterns: List[Tuple[str, str]] = [
            (r"no matching distribution found", "pip 报告无匹配发行版（wheel 不可用）"),
            (
                r"could not find a version that satisfies the requirement",
                "pip 报告无可用版本满足要求（wheel 不可用）",
            ),
            (
                r"no matching distributions available for your environment",
                "pip 报告目标环境缺少可用二进制发行版（wheel 不可用）",
            ),
            # 依赖冲突也可能是因为某些依赖只有源码可用
            (
                r"cannot install .* because these package versions have conflicting dependencies",
                "pip 报告依赖冲突（可能某些依赖无可用 wheel）",
            ),
            (
                r"resolutionimpossible",
                "pip 依赖解析失败（可能某些包无可用 wheel）",
            ),
        ]

        for err in errors:
            combined = "\n".join(
                [
                    str(err.get("message") or ""),
                    str(err.get("stderr") or ""),
                    str(err.get("stdout") or ""),
                ]
            ).lower()
            for pattern, reason in patterns:
                if re.search(pattern, combined):
                    return reason
        return None

    @staticmethod
    def _extract_failed_packages(errors: List[Dict[str, Any]]) -> List[str]:
        """从 pip 错误输出中提取无法找到 wheel 的包名列表。

        解析诸如以下的错误信息：
        - "Could not find a version that satisfies the requirement pkg1, pkg2..."
        - "No matching distribution found for pkg1, pkg2..."
        """
        if not errors:
            return []

        failed_packages = []

        for err in errors:
            stderr = str(err.get("stderr") or "")
            stdout = str(err.get("stdout") or "")
            combined = stderr + "\n" + stdout

            # 查找特定的错误模式
            # 模式1: "Could not find a version that satisfies the requirement xxx"
            # 模式2: "No matching distribution found for xxx"
            satisfaction_match = re.search(
                r"could not find a version that satisfies the requirement\s+([^\n]+)",
                combined, re.IGNORECASE
            )
            if satisfaction_match:
                # 提取包名列表（逗号分隔）
                pkg_str = satisfaction_match.group(1)
                # 移除版本约束，只保留包名
                pkgs = re.findall(r"([a-zA-Z0-9_-]+)(?:[=<>!~][^,]*)?", pkg_str)
                failed_packages.extend(p.strip() for p in pkgs if p.strip())

            distribution_match = re.search(
                r"no matching distribution found for\s+([^\n]+)",
                combined, re.IGNORECASE
            )
            if distribution_match:
                pkg_str = distribution_match.group(1)
                pkgs = re.findall(r"([a-zA-Z0-9_-]+)(?:[=<>!~][^,]*)?", pkg_str)
                failed_packages.extend(p.strip() for p in pkgs if p.strip())

            # 模式3: 依赖冲突 "Cannot install pkg1, pkg2... because these package versions have conflicting dependencies"
            conflict_match = re.search(
                r"cannot install\s+(.+?)\s+because these package versions have conflicting dependencies",
                combined, re.IGNORECASE | re.DOTALL
            )
            if conflict_match:
                pkg_str = conflict_match.group(1)
                # 提取包名（格式：package==version），过滤掉连接词
                pkgs = re.findall(r"([a-zA-Z0-9_-]+)==[^,\s]+", pkg_str)
                # 过滤掉非包名的词（如 'and'）
                skip_words = {'and', 'or', 'not'}
                failed_packages.extend(
                    p.strip() for p in pkgs 
                    if p.strip() and p.strip().lower() not in skip_words
                )

        # 去重并返回
        return list(dict.fromkeys(failed_packages))  # 保持顺序去重

    def _run_with_retries(self, cmd: List[str], stage: str) -> Dict[str, Any]:
        """Run a pip command with retry policy and structured error collection."""
        errors: List[Dict[str, Any]] = []

        for attempt in range(1, self.max_attempts + 1):
            if self.verbose:
                print(f"[{stage}] [Attempt {attempt}/{self.max_attempts}] Starting pip download...")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=self.command_timeout
                )

                if self.verbose and result.stdout:
                    print(result.stdout)

                return {
                    "success": True,
                    "output": result.stdout,
                    "attempts": attempt,
                    "errors": []
                }

            except subprocess.TimeoutExpired as exc:
                error_msg = (
                    f"[{stage}] Attempt {attempt}/{self.max_attempts} timed out after "
                    f"{self.command_timeout or 'unknown'} seconds."
                )
                errors.append({
                    "stage": stage,
                    "type": "timeout",
                    "message": error_msg,
                    "stdout": exc.stdout,
                    "stderr": exc.stderr
                })
                print(error_msg, file=sys.stderr)

            except subprocess.CalledProcessError as exc:
                error_msg = (
                    f"[{stage}] Attempt {attempt}/{self.max_attempts} failed with exit code {exc.returncode}."
                )
                errors.append({
                    "stage": stage,
                    "type": "process_error",
                    "message": error_msg,
                    "stdout": exc.stdout,
                    "stderr": exc.stderr
                })
                print(error_msg, file=sys.stderr)

            except OSError as exc:
                error_msg = (
                    f"[{stage}] Attempt {attempt}/{self.max_attempts} could not start pip: {exc}"
                )
                errors.append({
                    "stage": stage,
                    "type": "os_error",
                    "message": error_msg,
                    "stdout": None,
                    "stderr": str(exc)
                })
                print(error_msg, file=sys.stderr)

            if attempt < self.max_attempts:
                wait_time = self.retry_delay * attempt
                if wait_time > 0:
                    if self.verbose:
                        print(f"[{stage}] Retrying in {wait_time:.1f}s...", file=sys.stderr)
                    time.sleep(wait_time)

        last_error = errors[-1] if errors else {"message": f"[{stage}] Unknown error"}
        return {
            "success": False,
            "error": last_error["message"],
            "errors": errors,
            "attempts": self.max_attempts
        }

    def download_from_requirements(
        self,
        requirements_file: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Download packages from requirements.txt

        Args:
            requirements_file: Path to requirements.txt
            dry_run: If True, only show what would be downloaded

        Returns:
            Dictionary with download results
        """
        cmd = self._build_pip_command(["-r", requirements_file], dry_run=dry_run)
        root_requirements = self._read_requirements_file(Path(requirements_file))
        return self._execute_download(
            cmd,
            dry_run=dry_run,
            source_fallback_no_deps=False,
            root_requirements=root_requirements,
        )

    def download_resolved_requirements(
        self,
        resolved_packages: List[str],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Download packages using resolved requirement list.

        Args:
            resolved_packages: List of pinned requirements
            dry_run: If True, simulate download
        """
        if not resolved_packages:
            return {
                "success": False,
                "error": "No resolved packages provided",
                "downloaded_to": str(self.output_dir)
            }

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tmp_file:
            tmp_file.write("\n".join(resolved_packages))
            temp_path = tmp_file.name

        try:
            cmd = self._build_pip_command(["-r", temp_path], dry_run=dry_run)
            return self._execute_download(
                cmd,
                dry_run=dry_run,
                source_fallback_no_deps=True,
                root_requirements=resolved_packages,
            )
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

    def download_packages(
        self,
        packages: List[str],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Download specific packages

        Args:
            packages: List of package names
            dry_run: If True, only show what would be downloaded

        Returns:
            Dictionary with download results
        """
        cmd = self._build_pip_command(packages, dry_run=dry_run)
        return self._execute_download(
            cmd,
            dry_run=dry_run,
            source_fallback_no_deps=False,
            root_requirements=packages,
        )

    def _execute_download(
        self,
        cmd: List[str],
        dry_run: bool = False,
        source_fallback_no_deps: bool = False,
        root_requirements: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute pip download command

        Args:
            cmd: Complete pip command
            dry_run: If True, only show command without executing

        Returns:
            Dictionary with results
        """
        if self.verbose or dry_run:
            print(f"Command: {' '.join(cmd)}")

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "command": " ".join(cmd),
                "used_source_fallback": False,
                "fallback_reason": None
            }

        self._clear_source_fallback_report()
        wheel_stage_result = self._run_with_retries(cmd, stage="wheel_only")
        if wheel_stage_result["success"]:
            return {
                "success": True,
                "output": wheel_stage_result.get("output", ""),
                "downloaded_to": str(self.output_dir),
                "attempts": wheel_stage_result.get("attempts", 1),
                "errors": [],
                "used_source_fallback": False,
                "fallback_reason": None
            }

        fallback_reason = None
        has_only_binary = "--only-binary" in cmd and bool(self.only_binary)
        if has_only_binary:
            fallback_reason = self._detect_no_wheel_reason(wheel_stage_result.get("errors", []))

        if fallback_reason:
            failed_packages = self._extract_failed_packages(wheel_stage_result.get("errors", []))
            requirement_lookup = self._build_requirement_lookup_from_cmd(cmd)
            normalized_roots = root_requirements or list(requirement_lookup.values())
            root_lookup = self._build_requirement_lookup(normalized_roots)
            probe_results: Dict[str, Dict[str, Any]] = {}
            source_candidates: List[str] = []
            all_warnings: List[str] = []
            wheel_stage_errors = list(wheel_stage_result.get("errors", []))
            discovered_wheel_requirements: List[str] = []

            for failed_pkg in failed_packages:
                failed_key = canonicalize_name(failed_pkg)
                requirement = requirement_lookup.get(failed_key, failed_pkg)
                is_root = failed_key in root_lookup
                probe_info = self._probe_wheel_availability(
                    requirement,
                    is_root_requirement=is_root,
                )
                probe_results[failed_key] = {
                    "requirement": requirement,
                    "probe_result": probe_info.get("status"),
                    "probe_reason": probe_info.get("reason"),
                    "is_root_requirement": is_root,
                }
                if probe_info.get("status") == "no_wheel":
                    source_candidates.append(requirement)

            # 包模式下，若仅靠错误文本无法确认源码包，则从根包依赖做探测扫描
            if not source_candidates and normalized_roots and not source_fallback_no_deps:
                discovery = self._discover_source_candidates_from_roots(normalized_roots, probe_results)
                source_candidates.extend(discovery.get("source_candidates", []))
                discovered_wheel_requirements.extend(discovery.get("wheel_requirements", []))
                all_warnings.extend(discovery.get("warnings", []))

            # 对已确认 wheel 可用的根包补下载 no-deps wheel，避免根包误落入源码流程
            root_wheel_download = {"downloaded": [], "failed": [], "warnings": [], "errors": []}
            if normalized_roots and not source_fallback_no_deps:
                root_wheel_download = self._download_root_wheels_no_deps(normalized_roots, probe_results)
                all_warnings.extend(root_wheel_download.get("warnings", []))
                wheel_stage_errors.extend(root_wheel_download.get("errors", []))

            dep_wheel_preload = {"downloaded": [], "failed": [], "warnings": [], "errors": [], "promote_to_source": []}
            if discovered_wheel_requirements and not source_fallback_no_deps:
                dep_wheel_preload = self._download_dependency_wheels_no_deps(
                    discovered_wheel_requirements,
                    probe_results,
                )
                all_warnings.extend(dep_wheel_preload.get("warnings", []))
                wheel_stage_errors.extend(dep_wheel_preload.get("errors", []))
                source_candidates.extend(dep_wheel_preload.get("promote_to_source", []))

            source_candidates = list(dict.fromkeys(source_candidates))
            if self.verbose:
                print(f"[source_fallback] Extracted failed packages: {failed_packages}")
                print(f"[source_fallback] Confirmed source candidates: {source_candidates}")
                print(f"[source_fallback] source_fallback_no_deps: {source_fallback_no_deps}")
                if root_wheel_download.get("downloaded"):
                    print(f"[source_fallback] Root wheels(no-deps) downloaded: {root_wheel_download['downloaded']}")
                if dep_wheel_preload.get("downloaded"):
                    print(f"[source_fallback] Dependency wheels(no-deps) downloaded: {dep_wheel_preload['downloaded']}")

            if source_candidates:
                merged_stage_result = dict(wheel_stage_result)
                merged_stage_result["errors"] = wheel_stage_errors
                return self._execute_separate_strategy(
                    source_candidates=source_candidates,
                    wheel_stage_result=merged_stage_result,
                    fallback_reason=fallback_reason,
                    probe_results=probe_results,
                )

            fallback_report = {
                "strategy": "confirmed_probe_only",
                "target_python_version": self.python_version,
                "fallback_reason": fallback_reason,
                "source_packages": {},
                "candidate_probes": probe_results,
                "root_wheels_downloaded": root_wheel_download.get("downloaded", []),
                "dependency_wheels_downloaded": dep_wheel_preload.get("downloaded", []),
                "warnings": ["未确认到无 wheel 包，为避免误判未执行源码回退"] + all_warnings,
                "errors_count": len(wheel_stage_errors),
            }
            self._write_source_fallback_report(fallback_report)
            first_stage_hint = self._extract_stage_hint(wheel_stage_result.get("errors", []))
            error_msg = "wheel-only 下载失败，且未探测到可确认的源码包候选。"
            if first_stage_hint:
                error_msg = f"{error_msg}\n{first_stage_hint}"

            return {
                "success": False,
                "error": error_msg,
                "errors": wheel_stage_errors,
                "downloaded_to": str(self.output_dir),
                "used_source_fallback": False,
                "fallback_reason": fallback_reason,
                "source_fallback_report": fallback_report,
            }

        first_stage_hint = self._extract_stage_hint(wheel_stage_result.get("errors", []))
        first_stage_error = wheel_stage_result.get("error", "Unknown error")
        if first_stage_hint and first_stage_hint not in first_stage_error:
            first_stage_error = f"{first_stage_error}\n{first_stage_hint}"

        return {
            "success": False,
            "error": first_stage_error,
            "errors": wheel_stage_result.get("errors", []),
            "downloaded_to": str(self.output_dir),
            "used_source_fallback": False,
            "fallback_reason": None
        }

    def get_downloaded_packages(self) -> List[Path]:
        """
        Get list of downloaded wheel files

        Returns:
            List of wheel file paths
        """
        if not self.output_dir.exists():
            return []

        wheels = list(self.output_dir.glob("*.whl"))
        tar_gz = list(self.output_dir.glob("*.tar.gz"))
        zip_files = list(self.output_dir.glob("*.zip"))

        return sorted(wheels + tar_gz + zip_files)

    def parse_wheel_filename(self, wheel_path: Path) -> Optional[Dict[str, str]]:
        """
        Parse wheel filename to extract metadata

        Args:
            wheel_path: Path to wheel file

        Returns:
            Dictionary with metadata or None if not a wheel
        """
        filename = wheel_path.name

        if not filename.endswith(".whl"):
            return None

        # Wheel filename format: {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
        parts = filename[:-4].split("-")

        if len(parts) < 5:
            return None

        return {
            "name": parts[0],
            "version": parts[1],
            "python": parts[-3],
            "abi": parts[-2],
            "platform": parts[-1],
            "filename": filename
        }
