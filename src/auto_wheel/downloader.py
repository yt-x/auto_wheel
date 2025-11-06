"""
Package download module
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
import json


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
        config_pip_args: Optional[List[str]] = None
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
        """
        self.python_version = python_version
        self.output_dir = Path(output_dir)
        self.platform = platform
        self.implementation = implementation
        self.abi = abi or self._get_abi_tag()
        self.only_binary = only_binary
        self.verbose = verbose
        self.config_pip_args = config_pip_args or []

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
        return self._execute_download(cmd, dry_run=dry_run)

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
        return self._execute_download(cmd, dry_run=dry_run)

    def _execute_download(
        self,
        cmd: List[str],
        dry_run: bool = False
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
                "command": " ".join(cmd)
            }

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            if self.verbose:
                print(result.stdout)

            return {
                "success": True,
                "output": result.stdout,
                "downloaded_to": str(self.output_dir)
            }

        except subprocess.CalledProcessError as e:
            error_msg = f"Download failed: {e.stderr}"
            print(error_msg, file=sys.stderr)
            return {
                "success": False,
                "error": error_msg,
                "stdout": e.stdout,
                "stderr": e.stderr
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
