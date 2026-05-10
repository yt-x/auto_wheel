"""
Requirements file generation module
"""

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple
from packaging.utils import canonicalize_name
from packaging.version import parse as parse_version

from .state_model import DependencyState


class RequirementsGenerator:
    """Generate requirements.txt from downloaded packages"""

    def __init__(self, output_dir: str, with_hashes: bool = False) -> None:
        """
        Initialize requirements generator

        Args:
            output_dir: Directory containing downloaded packages
            with_hashes: Include package hashes in requirements.txt
        """
        self.output_dir = Path(output_dir)
        self.with_hashes = with_hashes
        self.sources_dir = self.output_dir / "sources"
        self.source_report_path = self.output_dir / "source-fallback-report.json"
        self.source_report: Dict[str, Any] = {}
        self.last_summary: Dict[str, Any] = {}

    def generate_dependency_preview(
        self,
        requirements: List[str],
        python_version: str,
        platform: str,
        implementation: str,
        abi: str,
        resolver_state: Optional[Dict[str, Any]] = None,
        tree_json_file: str = "dependency-tree.json",
        tree_text_file: str = "dependency-tree.txt",
        coverage_report_file: str = "coverage-report.md",
    ) -> Dict[str, str]:
        """
        生成依赖树预览产物（不执行下载）。
        """
        sanitized = [line.strip() for line in requirements if line and line.strip()]
        dependencies: List[Dict[str, str]] = []
        for raw in sanitized:
            pkg_name = self._extract_requirement_name(raw)
            dependencies.append(
                {
                    "requirement": raw,
                    "name": pkg_name,
                    "state": DependencyState.RESOLVED.value,
                    "note": "解析完成，待下载阶段确认 wheel/source 可用性",
                }
            )

        payload = {
            "target": {
                "python_version": python_version,
                "platform": platform,
                "implementation": implementation,
                "abi": abi,
            },
            "resolver_state": resolver_state or {},
            "summary": {
                "total_dependencies": len(dependencies),
                "resolved_dependencies": len(dependencies),
            },
            "dependencies": dependencies,
        }

        tree_json_path = self.output_dir / tree_json_file
        tree_text_path = self.output_dir / tree_text_file
        coverage_report_path = self.output_dir / coverage_report_file
        self.output_dir.mkdir(parents=True, exist_ok=True)

        tree_json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        lines = [
            f"target: py{python_version} / {platform} / {implementation}-{abi}",
            "dependencies:",
        ]
        for dep in dependencies:
            lines.append(f"- {dep['name']} ({dep['requirement']}) [{dep['state']}]")
        tree_text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        report_lines = [
            "# 依赖覆盖预览报告",
            "",
            f"- 目标 Python: `{python_version}`",
            f"- 目标平台: `{platform}`",
            f"- 实现/ABI: `{implementation}` / `{abi}`",
            f"- 解析依赖数: `{len(dependencies)}`",
            "",
            "## 当前状态说明",
            f"- `resolved`: `{len(dependencies)}`（已解析，待下载阶段验证 wheel/source 可用性）",
            "- `wheel_ready`: `0`（预览阶段不判定）",
            "- `source_required`: `0`（预览阶段不判定）",
            "- `unresolved`: `0`（预览阶段不判定）",
            "",
            "## 依赖清单",
        ]
        for dep in dependencies:
            report_lines.append(f"- `{dep['requirement']}` -> `{dep['state']}`")
        coverage_report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

        return {
            "tree_json": str(tree_json_path),
            "tree_text": str(tree_text_path),
            "coverage_report": str(coverage_report_path),
        }

    def generate(
        self,
        output_file: str = "requirements-offline.txt",
        sources_file: str = "sources-offline.txt",
        source_guide_file: str = "SOURCE_INSTALL_GUIDE.md",
        resolved_requirements: Optional[List[str]] = None,
        reconciliation_file: str = "manifest-reconciliation.json",
    ) -> str:
        """
        Generate requirements.txt from downloaded packages

        Args:
            output_file: Name of output requirements file

        Returns:
            Path to generated requirements file
        """
        self._prepare_sources_directory()
        self.source_report = self._load_source_fallback_report()
        wheel_packages = self._get_packages_info()
        source_packages = self._get_source_packages_info()

        prepared_lock_requirements = self._prepare_resolved_requirements(resolved_requirements)
        lock_output_requirements = [item["requirement"] for item in prepared_lock_requirements]
        normalized_lock_requirements = [item["normalized"] for item in prepared_lock_requirements]
        manifest_mode = "lock" if lock_output_requirements else "non_lock"

        if not wheel_packages and not source_packages and not lock_output_requirements:
            raise ValueError(f"No packages found in {self.output_dir}")

        output_path = self.output_dir / output_file
        sources_path = self.output_dir / sources_file
        guide_path = self.output_dir / source_guide_file
        reconciliation_path = self.output_dir / reconciliation_file

        if lock_output_requirements:
            offline_requirements = lock_output_requirements
        else:
            offline_requirements = self._build_requirements_from_wheels(wheel_packages)

        wheel_hashes = self._build_wheel_hash_lookup(wheel_packages)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Generated offline requirements file\n")
            f.write(
                f"# Install in an activated virtual environment with: "
                f"python -m pip install --no-index --find-links={self.output_dir.name} -r {output_file}\n"
            )
            f.write(f"# Manifest mode: {manifest_mode}\n")
            if manifest_mode == "lock":
                f.write("# This file is generated from resolver lock output.\n")
            else:
                f.write("# This file is generated by scanning downloaded wheel files.\n")
            f.write("#\n")
            f.write("# Note: This file contains exact versions of all downloaded packages\n\n")

            for requirement in offline_requirements:
                normalized_key = self._normalize_requirement_for_compare(requirement)
                hash_value = wheel_hashes.get(normalized_key) if normalized_key else None
                if self.with_hashes and hash_value:
                    f.write(f"{requirement} \\\n")
                    f.write(f"    --hash=sha256:{hash_value}\n")
                else:
                    f.write(f"{requirement}\n")

        if source_packages:
            self._write_sources_manifest(source_packages, sources_path, self.source_report)
            self._write_source_install_guide(
                source_packages,
                guide_path,
                output_file,
                sources_file,
                self.source_report,
            )
        else:
            if sources_path.exists():
                sources_path.unlink()
            if guide_path.exists():
                guide_path.unlink()

        reconciliation = self._build_manifest_reconciliation(
            lock_requirements=normalized_lock_requirements,
            wheel_packages=wheel_packages,
            source_packages=source_packages,
            manifest_mode=manifest_mode,
        )
        reconciliation_path.write_text(
            json.dumps(reconciliation, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        self.last_summary = {
            "requirements_file": str(output_path),
            "sources_file": str(sources_path),
            "source_guide_file": str(guide_path),
            "reconciliation_file": str(reconciliation_path),
            "manifest_mode": manifest_mode,
            "wheel_count": len(wheel_packages),
            "source_count": len(source_packages),
            "sources_dir": str(self.sources_dir),
            "source_report_file": str(self.source_report_path),
        }

        return str(output_path)

    def _load_source_fallback_report(self) -> Dict[str, Any]:
        """Load source fallback report if present."""
        if not self.source_report_path.exists():
            return {}
        try:
            with open(self.source_report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _prepare_sources_directory(self) -> None:
        """
        Move source distributions into a dedicated directory.
        """
        self.sources_dir.mkdir(parents=True, exist_ok=True)

        for pattern in ("*.tar.gz", "*.zip"):
            for sdist_path in self.output_dir.glob(pattern):
                target_path = self.sources_dir / sdist_path.name
                if target_path.exists():
                    target_path.unlink()
                sdist_path.replace(target_path)

    def _write_sources_manifest(
        self,
        source_packages: Dict[str, Dict[str, str]],
        manifest_path: Path,
        source_report: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Write source package manifest used for manual/offline handling.
        """
        report_sources = (source_report or {}).get("source_packages") or {}
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write("# Source packages that require manual/offline build handling\n")
            f.write("# Format: package==version  # file:<filename> [sha256:<hash>] [resolver:<source>] [probe:<status>]\n\n")
            for pkg_name, pkg_info in sorted(source_packages.items()):
                requirement = f"{pkg_name}=={pkg_info['version']}"
                suffix = f"  # file:{pkg_info['filename']}"
                if pkg_info.get('hash'):
                    suffix += f" sha256:{pkg_info['hash']}"
                pkg_report = report_sources.get(canonicalize_name(pkg_name))
                if pkg_report and pkg_report.get("dependency_source"):
                    suffix += f" resolver:{pkg_report['dependency_source']}"
                probe_status = (pkg_report or {}).get("probe_result") or "no_wheel"
                suffix += f" probe:{probe_status}"
                f.write(f"{requirement}{suffix}\n")

    def _write_source_install_guide(
        self,
        source_packages: Dict[str, Dict[str, str]],
        guide_path: Path,
        requirements_file: str,
        sources_file: str,
        source_report: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Write manual guide for source package offline installation.
        """
        report_sources = (source_report or {}).get("source_packages") or {}
        report_warnings = (source_report or {}).get("warnings") or []

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

        lines.extend([
            "",
            "## 6. 源码包逐项处理建议",
        ])

        for pkg_name, pkg_info in sorted(source_packages.items()):
            pkg_report = report_sources.get(canonicalize_name(pkg_name)) or {}
            dep_source = pkg_report.get("dependency_source", "unknown")
            probe_status = pkg_report.get("probe_result", "no_wheel")
            dependencies = pkg_report.get("dependencies") or []
            source_dependencies = pkg_report.get("source_dependencies") or []
            failed_dependencies = pkg_report.get("failed_wheel_dependencies") or []

            lines.append(f"### {pkg_name}=={pkg_info['version']}")
            lines.append(f"- 源码文件：`sources/{pkg_info['filename']}`")
            lines.append(f"- 依赖解析来源：`{dep_source}`")
            lines.append(f"- 探测结论：`{probe_status}`")
            if dependencies:
                lines.append(f"- 解析到依赖数量：{len(dependencies)}")
            else:
                lines.append("- 解析到依赖数量：0（可直接尝试构建）")
            if source_dependencies:
                lines.append(f"- 需要源码处理的依赖：{', '.join(source_dependencies)}")
            if failed_dependencies:
                lines.append(f"- wheel 下载失败依赖：{', '.join(failed_dependencies)}")
            lines.extend([
                "- 建议命令：",
                f"  - `python -m pip wheel --no-index --no-deps --wheel-dir=.wheels sources/{pkg_info['filename']}`",
                f"  - `python -m pip install --no-index --find-links=.wheels {pkg_name}=={pkg_info['version']}`",
                "",
            ])

        if report_warnings:
            lines.append("## 7. 回退过程告警")
            for warning in report_warnings:
                lines.append(f"- {warning}")

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

    @staticmethod
    def _normalize_requirement_for_compare(requirement: str) -> Optional[str]:
        """将 requirement 规范化为 name==version，用于对账。"""
        line = requirement.strip()
        if not line or line.startswith("#"):
            return None
        if " \\" in line:
            line = line.split(" \\", 1)[0].strip()
        if " --hash=" in line:
            line = line.split(" --hash=", 1)[0].strip()
        if ";" in line:
            line = line.split(";", 1)[0].strip()
        if "==" not in line:
            return None
        name, version = line.split("==", 1)
        name = name.strip().replace("_", "-").lower()
        version = version.strip()
        if not name or not version:
            return None
        return f"{name}=={version}"

    @classmethod
    def _prepare_resolved_requirements(cls, requirements: Optional[List[str]]) -> List[Dict[str, str]]:
        """准备锁定依赖：保留输出文本，并提供规范化键用于对账去重。"""
        prepared: List[Dict[str, str]] = []
        seen = set()
        for raw in requirements or []:
            requirement_line = raw.strip()
            if not requirement_line or requirement_line.startswith("#"):
                continue
            normalized = cls._normalize_requirement_for_compare(requirement_line)
            if not normalized or normalized in seen:
                continue
            prepared.append(
                {
                    "requirement": requirement_line,
                    "normalized": normalized,
                }
            )
            seen.add(normalized)
        return prepared

    @staticmethod
    def _build_requirements_from_wheels(wheel_packages: Dict[str, Dict[str, str]]) -> List[str]:
        """从扫描到的 wheel 信息构建 requirements 列表。"""
        return [f"{pkg_name}=={pkg_info['version']}" for pkg_name, pkg_info in sorted(wheel_packages.items())]

    @staticmethod
    def _build_wheel_hash_lookup(wheel_packages: Dict[str, Dict[str, str]]) -> Dict[str, str]:
        """构建 requirement -> sha256 的映射。"""
        lookup: Dict[str, str] = {}
        for pkg_name, info in wheel_packages.items():
            hash_value = info.get("hash")
            if not hash_value:
                continue
            key = f"{pkg_name.lower()}=={info['version']}"
            lookup[key] = hash_value
        return lookup

    @classmethod
    def _build_artifact_requirement_sets(
        cls,
        wheel_packages: Dict[str, Dict[str, str]],
        source_packages: Dict[str, Dict[str, str]],
    ) -> Tuple[set, set]:
        """构建 wheel/source 产物的规范化 requirement 集合。"""
        wheel_set = {
            cls._normalize_requirement_for_compare(f"{name}=={info['version']}")
            for name, info in wheel_packages.items()
        }
        source_set = {
            cls._normalize_requirement_for_compare(f"{name}=={info['version']}")
            for name, info in source_packages.items()
        }
        return {x for x in wheel_set if x}, {x for x in source_set if x}

    @classmethod
    def _build_manifest_reconciliation(
        cls,
        lock_requirements: List[str],
        wheel_packages: Dict[str, Dict[str, str]],
        source_packages: Dict[str, Dict[str, str]],
        manifest_mode: str,
    ) -> Dict[str, Any]:
        """构建锁定清单与产物的一致性对账结果。"""
        wheel_set, source_set = cls._build_artifact_requirement_sets(wheel_packages, source_packages)
        lock_set = set(lock_requirements)

        if not lock_set:
            return {
                "manifest_mode": manifest_mode,
                "lock_requirements": [],
                "missing_from_artifacts": [],
                "source_only": [],
                "extra_artifacts_not_in_lock": [],
                "note": "No resolver lock provided; running in non-lock mode.",
            }

        artifacts_union = wheel_set | source_set
        source_only = sorted(lock_set & source_set - wheel_set)
        missing = sorted(lock_set - artifacts_union)
        extra = sorted(artifacts_union - lock_set)

        return {
            "manifest_mode": manifest_mode,
            "lock_requirements": sorted(lock_set),
            "missing_from_artifacts": missing,
            "source_only": source_only,
            "extra_artifacts_not_in_lock": extra,
        }

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

    @staticmethod
    def _extract_requirement_name(requirement_line: str) -> str:
        """从 requirement 行提取包名（用于预览展示）。"""
        line = requirement_line.strip()
        for splitter in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if splitter in line:
                return line.split(splitter, 1)[0].strip()
        if ";" in line:
            return line.split(";", 1)[0].strip()
        return line

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

    def run_installability_check(
        self,
        requirements_file: str = "requirements-offline.txt",
        report_file: str = "installability-report.md",
        python_executable: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        在联网环境对离线包执行可安装性预演。
        """
        python_bin = python_executable or sys.executable
        command = [
            python_bin,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--no-index",
            "--find-links=.",
            "-r",
            requirements_file,
        ]

        result = subprocess.run(
            command,
            cwd=str(self.output_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        success = result.returncode == 0
        report_path = self.output_dir / report_file
        now_str = datetime.now(timezone.utc).isoformat()

        lines = [
            "# 离线可安装性预演报告",
            "",
            f"- 执行时间(UTC): `{now_str}`",
            f"- 结果: `{'PASS' if success else 'FAIL'}`",
            f"- 工作目录: `{self.output_dir}`",
            f"- 命令: `{' '.join(command)}`",
        ]
        if context:
            lines.append("- 上下文:")
            for key, value in context.items():
                lines.append(f"  - `{key}`: `{value}`")

        lines.extend(
            [
                "",
                "## 标准输出",
                "```text",
                (result.stdout or "").strip(),
                "```",
                "",
                "## 标准错误",
                "```text",
                (result.stderr or "").strip(),
                "```",
            ]
        )
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return {
            "success": success,
            "returncode": result.returncode,
            "report_file": str(report_path),
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
