"""
Requirements file generation module
"""

import hashlib
import shutil
from pathlib import Path
from typing import Dict, Optional, Any
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
        self.sources_dir = self.output_dir / "sources"
        self.last_summary: Dict[str, Any] = {}

    def generate(
        self,
        output_file: str = "requirements-offline.txt",
        sources_file: str = "sources-offline.txt",
        source_guide_file: str = "SOURCE_INSTALL_GUIDE.md"
    ) -> str:
        """
        Generate requirements.txt from downloaded packages

        Args:
            output_file: Name of output requirements file

        Returns:
            Path to generated requirements file
        """
        self._prepare_sources_directory()
        wheel_packages = self._get_packages_info()
        source_packages = self._get_source_packages_info()

        if not wheel_packages and not source_packages:
            raise ValueError(f"No packages found in {self.output_dir}")

        output_path = self.output_dir / output_file
        sources_path = self.output_dir / sources_file
        guide_path = self.output_dir / source_guide_file

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Generated offline requirements file\n")
            f.write(
                f"# Install in an activated virtual environment with: "
                f"python -m pip install --no-index --find-links={self.output_dir.name} -r {output_file}\n"
            )
            f.write("# This file contains wheel-based dependencies only.\n")
            f.write("#\n")
            f.write("# Note: This file contains exact versions of all downloaded packages\n\n")

            for pkg_name, pkg_info in sorted(wheel_packages.items()):
                requirement = f"{pkg_name}=={pkg_info['version']}"

                if self.with_hashes and pkg_info.get('hash'):
                    f.write(f"{requirement} \\\n")
                    f.write(f"    --hash=sha256:{pkg_info['hash']}\n")
                else:
                    f.write(f"{requirement}\n")

        if source_packages:
            self._write_sources_manifest(source_packages, sources_path)
            self._write_source_install_guide(source_packages, guide_path, output_file, sources_file)
        else:
            if sources_path.exists():
                sources_path.unlink()
            if guide_path.exists():
                guide_path.unlink()

        self.last_summary = {
            "requirements_file": str(output_path),
            "sources_file": str(sources_path),
            "source_guide_file": str(guide_path),
            "wheel_count": len(wheel_packages),
            "source_count": len(source_packages),
            "sources_dir": str(self.sources_dir)
        }

        return str(output_path)

    def _prepare_sources_directory(self) -> None:
        """
        Move source distributions into a dedicated directory.
        """
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        for child in self.sources_dir.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)

        for pattern in ("*.tar.gz", "*.zip"):
            for sdist_path in self.output_dir.glob(pattern):
                target_path = self.sources_dir / sdist_path.name
                if target_path.exists():
                    target_path.unlink()
                sdist_path.replace(target_path)

    def _write_sources_manifest(self, source_packages: Dict[str, Dict[str, str]], manifest_path: Path) -> None:
        """
        Write source package manifest used for manual/offline handling.
        """
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write("# Source packages that require manual/offline build handling\n")
            f.write("# Format: package==version  # file:<filename> [sha256:<hash>]\n\n")
            for pkg_name, pkg_info in sorted(source_packages.items()):
                requirement = f"{pkg_name}=={pkg_info['version']}"
                suffix = f"  # file:{pkg_info['filename']}"
                if pkg_info.get('hash'):
                    suffix += f" sha256:{pkg_info['hash']}"
                f.write(f"{requirement}{suffix}\n")

    def _write_source_install_guide(
        self,
        source_packages: Dict[str, Dict[str, str]],
        guide_path: Path,
        requirements_file: str,
        sources_file: str
    ) -> None:
        """
        Write manual guide for source package offline installation.
        """
        lines = [
            "# 源码包离线安装指引",
            "",
            "检测到以下依赖仅有源码包（sdist），需要先手工处理，再安装 wheel 依赖。",
            "",
            "## 1. 前置条件",
            "- 已激活虚拟环境（venv/conda）",
            "- 可用 Python 构建工具链（setuptools/wheel/build backend 及编译工具）",
            "",
            "## 2. 建议处理顺序",
            f"1) 先查看清单：`{sources_file}`",
            "2) 在当前目录处理 `sources/` 里的源码包（建议先构建 wheel，再安装）",
            "3) 完成源码包后，执行常规离线安装命令",
            "",
            "## 3. 常用命令示例（按需替换文件名）",
            "```bash",
            "# 在 downloads 目录下执行",
            "python -m pip wheel --no-index --no-deps --wheel-dir=.wheels sources/<source-package>.tar.gz",
            "python -m pip install --no-index --find-links=.wheels <package_name>==<version>",
            "",
            f"# 源码包处理完成后，再安装 wheel 依赖",
            f"python -m pip install --no-index --find-links=. -r {requirements_file}",
            "```",
            "",
            "## 4. 兼容旧式 setup.py 包（仅当上面方式不可用）",
            "```bash",
            "tar -xf sources/<source-package>.tar.gz",
            "cd <source-package-dir>",
            "python setup.py install",
            "```",
            "",
            "## 5. 本次检测到的源码包",
        ]

        for pkg_name, pkg_info in sorted(source_packages.items()):
            lines.append(f"- {pkg_name}=={pkg_info['version']} ({pkg_info['filename']})")

        with open(guide_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines) + "\n")

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

        return packages

    def _get_source_packages_info(self) -> Dict[str, Dict[str, str]]:
        """
        Extract source package information from the dedicated sources directory.
        """
        packages: Dict[str, Dict[str, str]] = {}

        for sdist_path in list(self.sources_dir.glob("*.tar.gz")) + list(self.sources_dir.glob("*.zip")):
            info = self._parse_sdist_filename(sdist_path)
            if not info:
                continue

            pkg_name = info['name'].replace('_', '-')
            if pkg_name in packages:
                existing_version = parse_version(packages[pkg_name]['version'])
                new_version = parse_version(info['version'])
                if new_version <= existing_version:
                    continue

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

    def generate_install_script(
        self,
        requirements_file: str = "requirements-offline.txt",
        sources_file: str = "sources-offline.txt",
        source_guide_file: str = "SOURCE_INSTALL_GUIDE.md"
    ) -> str:
        """
        Generate shell/batch scripts for offline installation.

        The generated scripts only allow installation in an activated
        virtual environment (venv/conda) to avoid polluting global Python.

        Args:
            requirements_file: Name of requirements file

        Returns:
            Path to generated install script
        """
        script_path = self.output_dir / "install.sh"

        script_content = f"""#!/bin/bash
# 离线安装脚本（仅允许在虚拟环境中安装）
# 由 auto-wheel 自动生成

set -euo pipefail

REQ_FILE="{requirements_file}"
SRC_FILE="{sources_file}"
GUIDE_FILE="{source_guide_file}"
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -n "${{VIRTUAL_ENV:-}}" && -x "${{VIRTUAL_ENV}}/bin/python" ]]; then
    PYTHON_BIN="${{VIRTUAL_ENV}}/bin/python"
elif [[ -n "${{CONDA_PREFIX:-}}" && -x "${{CONDA_PREFIX}}/bin/python" ]]; then
    PYTHON_BIN="${{CONDA_PREFIX}}/bin/python"
else
    echo "未检测到已激活的虚拟环境（venv/conda），为避免安装到全局环境，脚本已停止。" >&2
    echo "建议执行以下步骤：" >&2
    echo "  1) python -m venv .venv" >&2
    echo "  2) source .venv/bin/activate  (Windows PowerShell: .venv\\Scripts\\Activate.ps1)" >&2
    echo "  3) python -m pip install --no-index --find-links=. -r $REQ_FILE" >&2
    exit 1
fi

if [[ -f "$SRC_FILE" ]] && grep -Eq '^[[:space:]]*[^#[:space:]]' "$SRC_FILE"; then
    echo "检测到源码包清单：$SRC_FILE" >&2
    echo "为避免半安装状态，脚本已停止自动安装。" >&2
    echo "请先按 $GUIDE_FILE 处理源码包，然后重新执行本脚本。" >&2
    exit 2
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
REM 离线安装脚本（仅允许在虚拟环境中安装）
REM 由 auto-wheel 自动生成
setlocal enabledelayedexpansion

set "REQ_FILE={requirements_file}"
set "SRC_FILE={sources_file}"
set "GUIDE_FILE={source_guide_file}"
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" >nul

set "EXIT_CODE=0"
set "PYTHON_EXE="
set "HAS_SOURCE=0"

if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\\Scripts\\python.exe" (
    set "PYTHON_EXE=%VIRTUAL_ENV%\\Scripts\\python.exe"
)

if not defined PYTHON_EXE if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\\python.exe" (
    set "PYTHON_EXE=%CONDA_PREFIX%\\python.exe"
)

if not defined PYTHON_EXE (
    echo 未检测到已激活的虚拟环境（venv/conda），为避免安装到全局环境，脚本已停止。
    echo 建议执行以下步骤：
    echo   1^) python -m venv .venv
    echo   2^) .venv\\Scripts\\Activate.ps1  或  .venv\\Scripts\\activate.bat
    echo   3^) python -m pip install --no-index --find-links=. -r "%REQ_FILE%"
    set "EXIT_CODE=1"
    goto :finish
)

if exist "%SRC_FILE%" (
    for /f "usebackq tokens=* delims=" %%L in ("%SRC_FILE%") do (
        set "LINE=%%L"
        if not "!LINE!"=="" if not "!LINE:~0,1!"=="#" (
            set "HAS_SOURCE=1"
            goto :source_detected
        )
    )
)

:source_detected
if "%HAS_SOURCE%"=="1" (
    echo 检测到源码包清单：%SRC_FILE%
    echo 为避免半安装状态，脚本已停止自动安装。
    echo 请先按 %GUIDE_FILE% 处理源码包，然后重新执行本脚本。
    set "EXIT_CODE=2"
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
