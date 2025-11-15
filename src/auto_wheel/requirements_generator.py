"""
Requirements file generation module
"""

import hashlib
from pathlib import Path
from typing import Dict, Optional
from packaging.version import parse as parse_version


class RequirementsGenerator:
    """Generate requirements.txt from downloaded packages"""

    def __init__(self, output_dir: str, with_hashes: bool = False):
        """
        Initialize requirements generator

        Args:
            output_dir: Directory containing downloaded packages
            with_hashes: Include package hashes in requirements.txt
        """
        self.output_dir = Path(output_dir)
        self.with_hashes = with_hashes

    def generate(self, output_file: str = "requirements-offline.txt") -> str:
        """
        Generate requirements.txt from downloaded packages

        Args:
            output_file: Name of output requirements file

        Returns:
            Path to generated requirements file
        """
        packages = self._get_packages_info()

        if not packages:
            raise ValueError(f"No packages found in {self.output_dir}")

        output_path = self.output_dir / output_file

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Generated offline requirements file\n")
            f.write(f"# Install with: pip install --no-index --find-links={self.output_dir.name} -r {output_file}\n")
            f.write("#\n")
            f.write("# Note: This file contains exact versions of all downloaded packages\n\n")

            for pkg_name, pkg_info in sorted(packages.items()):
                requirement = f"{pkg_name}=={pkg_info['version']}"

                if self.with_hashes and pkg_info.get('hash'):
                    f.write(f"{requirement} \\\n")
                    f.write(f"    --hash=sha256:{pkg_info['hash']}\n")
                else:
                    f.write(f"{requirement}\n")

        return str(output_path)

    def _get_packages_info(self) -> Dict[str, Dict[str, str]]:
        """
        Extract package information from downloaded files

        Returns:
            Dictionary mapping package names to their info
        """
        packages = {}

        # Find all wheel files
        for wheel_path in self.output_dir.glob("*.whl"):
            info = self._parse_wheel_filename(wheel_path)
            if info:
                pkg_name = info['name'].replace('_', '-')  # Normalize name

                # If package already exists, keep the one with higher version
                if pkg_name in packages:
                    existing_version = parse_version(packages[pkg_name]['version'])
                    new_version = parse_version(info['version'])
                    if new_version <= existing_version:
                        continue

                packages[pkg_name] = {
                    'version': info['version'],
                    'filename': wheel_path.name,
                    'hash': self._calculate_hash(wheel_path) if self.with_hashes else None
                }

        # Also handle source distributions if no wheel available
        for sdist_path in list(self.output_dir.glob("*.tar.gz")) + list(self.output_dir.glob("*.zip")):
            info = self._parse_sdist_filename(sdist_path)
            if info:
                pkg_name = info['name'].replace('_', '-')

                # Only add if no wheel exists for this package
                if pkg_name not in packages:
                    packages[pkg_name] = {
                        'version': info['version'],
                        'filename': sdist_path.name,
                        'hash': self._calculate_hash(sdist_path) if self.with_hashes else None
                    }

        return packages

    def _parse_wheel_filename(self, wheel_path: Path) -> Optional[Dict[str, str]]:
        """Parse wheel filename to extract package info"""
        filename = wheel_path.name

        if not filename.endswith(".whl"):
            return None

        # Wheel format: {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
        parts = filename[:-4].split("-")

        if len(parts) < 5:
            return None

        return {
            "name": parts[0],
            "version": parts[1],
        }

    def _parse_sdist_filename(self, sdist_path: Path) -> Optional[Dict[str, str]]:
        """Parse source distribution filename"""
        filename = sdist_path.name

        # Remove extensions
        if filename.endswith(".tar.gz"):
            name_version = filename[:-7]
        elif filename.endswith(".zip"):
            name_version = filename[:-4]
        else:
            return None

        # Try to split name and version
        # Format is usually: package-name-1.2.3
        parts = name_version.rsplit("-", 1)
        if len(parts) != 2:
            return None

        return {
            "name": parts[0],
            "version": parts[1],
        }

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file"""
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    def generate_install_script(self, requirements_file: str = "requirements-offline.txt") -> str:
        """
        Generate a shell script for offline installation

        Args:
            requirements_file: Name of requirements file

        Returns:
            Path to generated install script
        """
        script_path = self.output_dir / "install.sh"

        script_content = f"""#!/bin/bash
# 离线安装脚本（优先使用当前虚拟环境）
# 由 auto-wheel 自动生成

set -euo pipefail

REQ_FILE="{requirements_file}"
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -n "${{VIRTUAL_ENV:-}}" && -x "${{VIRTUAL_ENV}}/bin/python" ]]; then
    PYTHON_BIN="${{VIRTUAL_ENV}}/bin/python"
elif [[ -n "${{CONDA_PREFIX:-}}" && -x "${{CONDA_PREFIX}}/bin/python" ]]; then
    PYTHON_BIN="${{CONDA_PREFIX}}/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    echo "未找到可用的 Python 解释器，请先激活虚拟环境或将 python 加入 PATH。" >&2
    exit 1
fi

echo "使用 Python: $PYTHON_BIN"
"$PYTHON_BIN" -m pip install --no-index --find-links=. -r "$REQ_FILE"

echo "安装完成！"
"""

        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)

        # Make script executable on Unix-like systems
        try:
            script_path.chmod(0o755)
        except Exception:
            pass  # Windows doesn't support chmod

        # Also create a Windows batch file
        batch_path = self.output_dir / "install.bat"
        batch_content = f"""@echo off
chcp 65001 >nul
REM 离线安装脚本（优先使用当前虚拟环境）
REM 由 auto-wheel 自动生成
setlocal enabledelayedexpansion

set "REQ_FILE={requirements_file}"
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" >nul

set "EXIT_CODE=0"
set "PYTHON_EXE="

if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
    set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
)

if not defined PYTHON_EXE if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" (
    set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
)

if not defined PYTHON_EXE (
    for %%P in (python.exe py.exe) do (
        for /f "delims=" %%I in ('where %%P 2^>nul') do (
            set "PYTHON_EXE=%%I"
            goto :found_python
        )
    )
)

:found_python
if not defined PYTHON_EXE (
    echo 未能找到 Python，请先激活虚拟环境后再执行此脚本。
    set "EXIT_CODE=1"
    goto :finish
)

echo 使用 Python: %PYTHON_EXE%
"%PYTHON_EXE%" -m pip install --no-index --find-links=. -r "%REQ_FILE%"
if errorlevel 1 (
    echo 安装失败，请检查虚拟环境或 requirements 文件。
    set "EXIT_CODE=1"
    goto :finish
)

echo 安装完成！
set "EXIT_CODE=0"
goto :finish

:finish
popd
pause
exit /b %EXIT_CODE%
"""

        with open(batch_path, 'w', encoding='utf-8') as f:
            f.write(batch_content)

        return str(script_path)
