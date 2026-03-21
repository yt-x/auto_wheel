"""
Package download module
"""

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple


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
        max_attempts: int = 3,
        retry_delay: float = 3.0,
        command_timeout: Optional[int] = None
    ):
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
        self.max_attempts = max(1, max_attempts)
        self.retry_delay = max(0.0, retry_delay)
        self.command_timeout = command_timeout if command_timeout and command_timeout > 0 else None

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
    def _remove_target_constraints(cmd: List[str]) -> List[str]:
        """Return a copy of command without target interpreter/platform constraints."""
        filtered: List[str] = []
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
        """Build fallback command that allows sdist download under pip constraints."""
        without_only_binary = self._remove_only_binary(cmd)
        fallback_cmd = self._remove_target_constraints(without_only_binary)
        if source_fallback_no_deps and "--no-deps" not in fallback_cmd:
            fallback_cmd.append("--no-deps")
        return fallback_cmd

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
        return self._execute_download(cmd, dry_run=dry_run, source_fallback_no_deps=False)

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
            return self._execute_download(cmd, dry_run=dry_run, source_fallback_no_deps=True)
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
        return self._execute_download(cmd, dry_run=dry_run, source_fallback_no_deps=False)

    def _execute_download(
        self,
        cmd: List[str],
        dry_run: bool = False,
        source_fallback_no_deps: bool = False
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
            fallback_cmd = self._build_source_fallback_command(
                cmd,
                source_fallback_no_deps=source_fallback_no_deps
            )
            if self.verbose:
                print(
                    f"[source_fallback] Triggered because: {fallback_reason}. "
                    "Retrying without --only-binary and target constraints..."
                )
                print(f"[source_fallback] Command: {' '.join(fallback_cmd)}")

            source_stage_result = self._run_with_retries(fallback_cmd, stage="source_fallback")
            if source_stage_result["success"]:
                return {
                    "success": True,
                    "output": source_stage_result.get("output", ""),
                    "downloaded_to": str(self.output_dir),
                    "attempts": source_stage_result.get("attempts", 1),
                    "errors": wheel_stage_result.get("errors", []) + source_stage_result.get("errors", []),
                    "used_source_fallback": True,
                    "fallback_reason": fallback_reason
                }

            merged_errors = wheel_stage_result.get("errors", []) + source_stage_result.get("errors", [])
            fallback_hint = self._extract_stage_hint(source_stage_result.get("errors", []))
            error_msg = source_stage_result.get("error", "Source fallback failed.")
            if fallback_hint and fallback_hint not in error_msg:
                error_msg = f"{error_msg}\n{fallback_hint}"

            return {
                "success": False,
                "error": error_msg,
                "errors": merged_errors,
                "downloaded_to": str(self.output_dir),
                "used_source_fallback": True,
                "fallback_reason": fallback_reason
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
