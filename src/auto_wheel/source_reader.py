"""
依赖源文件读取模块 — 根据文件内容结构自动检测并解析
requirements.txt / pyproject.toml / 锁文件 三种输入格式。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


class SourceType(str, Enum):
    LOCK_FILE = "lock_file"
    PYPROJECT_TOML = "pyproject_toml"
    REQUIREMENTS_TXT = "requirements_txt"


_TYPE_PRIORITY: Dict[SourceType, int] = {
    SourceType.LOCK_FILE: 0,
    SourceType.PYPROJECT_TOML: 1,
    SourceType.REQUIREMENTS_TXT: 2,
}


_REQUIREMENT_LINE_PATTERN = re.compile(
    r"^\s*[A-Za-z0-9_.-]+(?:\s*[><=!~]=|[><]=?|!=)\s*[^\s;]+"
)


@dataclass
class DependencySource:
    source_type: SourceType
    source_path: Path
    requirements: List[str]
    is_pinned: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class SourceReader:
    """内容优先的依赖源读取器。不依赖文件名，按文件内容结构判定类型。"""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def read(self, path: str) -> DependencySource:
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"路径不存在: {path}")
        if p.is_dir():
            return self._read_directory(p)
        return self._parse(p)

    def _read_directory(self, dir_path: Path) -> DependencySource:
        best_source: Optional[DependencySource] = None
        best_priority = 999
        tried: List[str] = []

        for f in sorted(dir_path.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            try:
                source = self._parse(f)
            except ValueError as exc:
                tried.append(f"{f.name}: {exc}")
                continue
            priority = _TYPE_PRIORITY.get(source.source_type, 99)
            if priority < best_priority:
                best_priority = priority
                best_source = source

        if best_source is None:
            tried_detail = "\n".join(tried) if tried else "未找到任何文件"
            raise ValueError(
                f"目录 {dir_path} 中未找到可识别的依赖文件:\n{tried_detail}"
            )

        if self.verbose and best_source.warnings:
            for warning in best_source.warnings:
                print(f"[source_reader] {warning}")

        return best_source

    def _parse(self, file_path: Path) -> DependencySource:
        toml_data = self._try_parse_toml(file_path)

        if toml_data is not None:
            lock_source = self._try_parse_lock(toml_data, file_path)
            if lock_source is not None:
                return lock_source

            pyproject_source = self._try_parse_pyproject(toml_data, file_path)
            if pyproject_source is not None:
                return pyproject_source

        return self._try_parse_requirements(file_path)

    # ------------------------------------------------------------------
    # TOML 解析
    # ------------------------------------------------------------------

    @staticmethod
    def _try_parse_toml(file_path: Path) -> Optional[Dict[str, Any]]:
        if tomllib is None:
            return None
        try:
            with open(file_path, "rb") as fh:
                return tomllib.load(fh)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 锁文件 ([[package]] + name/version/source)
    # ------------------------------------------------------------------

    def _try_parse_lock(
        self,
        data: Dict[str, Any],
        file_path: Path,
    ) -> Optional[DependencySource]:
        packages = data.get("package")
        if not isinstance(packages, list):
            return None
        if len(packages) == 0:
            return DependencySource(
                source_type=SourceType.LOCK_FILE,
                source_path=file_path,
                requirements=[],
                is_pinned=True,
                metadata={"total_packages": 0, "skipped_non_registry": []},
                warnings=["锁文件未包含有效的 package 条目"],
            )

        requirements: List[str] = []
        warnings: List[str] = []
        skipped: List[str] = []
        skipped_reasons: Dict[str, str] = {}

        for entry in packages:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            version = entry.get("version")
            source = entry.get("source")

            if not name or not version:
                continue

            source_type, source_detail = self._classify_lock_source(source)
            if source_type == "registry":
                requirements.append(f"{name}=={version}")
            elif source_type == "skip":
                skipped.append(name)
                skipped_reasons[name] = source_detail
            else:
                warnings.append(f"锁文件中包 {name} 来源类型未知 (source={source}), 已跳过")

        if skipped:
            detail_parts = [f"{n}({skipped_reasons.get(n, 'non-registry')})" for n in skipped]
            warnings.append(
                f"锁文件中 {len(skipped)} 个包为非 registry 源, 已跳过: {', '.join(detail_parts)}"
            )

        if not requirements:
            warnings.append("锁文件未包含有效的 registry 类型 package 条目")

        return DependencySource(
            source_type=SourceType.LOCK_FILE,
            source_path=file_path,
            requirements=requirements,
            is_pinned=True,
            metadata={"total_packages": len(packages), "skipped_non_registry": skipped},
            warnings=warnings,
        )

    @staticmethod
    def _classify_lock_source(source: Any) -> tuple:
        if isinstance(source, dict):
            if "registry" in source:
                return ("registry", "registry")
            for key in ("git", "directory", "editable", "path"):
                if key in source:
                    return ("skip", key)
        return ("unknown", "unknown")

    # ------------------------------------------------------------------
    # pyproject.toml ([project].dependencies)
    # ------------------------------------------------------------------

    def _try_parse_pyproject(
        self,
        data: Dict[str, Any],
        file_path: Path,
    ) -> Optional[DependencySource]:
        project = data.get("project")
        if not isinstance(project, dict):
            return None

        dependencies = project.get("dependencies")
        if not isinstance(dependencies, list):
            return DependencySource(
                source_type=SourceType.PYPROJECT_TOML,
                source_path=file_path,
                requirements=[],
                is_pinned=False,
                metadata={
                    "project_name": project.get("name"),
                    "requires_python": project.get("requires-python"),
                },
                warnings=["pyproject.toml 中未找到 project.dependencies"],
            )

        requirements: List[str] = []
        warnings: List[str] = []
        for dep in dependencies:
            if isinstance(dep, str) and dep.strip():
                requirements.append(dep.strip())
            else:
                warnings.append(f"pyproject.toml 中存在非字符串依赖条目: {dep}")

        if not requirements:
            warnings.append("pyproject.toml 中 project.dependencies 为空列表")

        return DependencySource(
            source_type=SourceType.PYPROJECT_TOML,
            source_path=file_path,
            requirements=requirements,
            is_pinned=False,
            metadata={
                "project_name": project.get("name"),
                "requires_python": project.get("requires-python"),
            },
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # requirements.txt 文本格式
    # ------------------------------------------------------------------

    def _try_parse_requirements(self, file_path: Path) -> DependencySource:
        lines: List[str] = []
        warnings: List[str] = []
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"文件 {file_path.name} 不是有效的 UTF-8 文本, 无法解析")

        has_recognizable_line = False

        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("-r ") or line.startswith("--requirement "):
                nested = line.split(maxsplit=1)[1].strip()
                warnings.append(
                    f"{file_path.name} 包含递归引用 -r {nested}, 当前不支持自动展开"
                )
                continue

            if line.startswith("-") and not any(
                line.startswith(p) for p in ("-e", "--")
            ):
                continue

            lines.append(line)
            if not has_recognizable_line and self._looks_like_requirement(line):
                has_recognizable_line = True

        if not lines or not has_recognizable_line:
            raise ValueError(
                f"文件 {file_path.name} 中未检测到可识别的依赖声明, "
                f"请检查是否为合法的 requirements.txt / pyproject.toml / 锁文件"
            )

        return DependencySource(
            source_type=SourceType.REQUIREMENTS_TXT,
            source_path=file_path,
            requirements=lines,
            is_pinned=False,
            metadata={},
            warnings=warnings,
        )

    @staticmethod
    def _looks_like_requirement(line: str) -> bool:
        if _REQUIREMENT_LINE_PATTERN.match(line):
            return True
        try:
            Requirement(line)
            return True
        except Exception:
            pass
        if re.match(r"^\s*[A-Za-z0-9_.-]+\s*$", line):
            return True
        return False

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------

    @staticmethod
    def requirements_to_package_list(requirements: List[str]) -> List[str]:
        """从依赖列表提取纯包名列表, 用于日志/gui 展示。"""
        names: List[str] = []
        for req in requirements:
            try:
                names.append(canonicalize_name(Requirement(req).name))
            except Exception:
                match = re.match(r"^\s*([A-Za-z0-9_.-]+)", req)
                if match:
                    names.append(canonicalize_name(match.group(1)))
        return list(dict.fromkeys(names))
