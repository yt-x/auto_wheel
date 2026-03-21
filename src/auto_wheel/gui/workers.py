"""
后台线程：执行下载与离线脚本生成。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from ..config import Config
from ..downloader import WheelDownloader
from ..requirements_generator import RequirementsGenerator
from ..resolver import DependencyResolver
from ..utils import get_python_version_warning, validate_python_version


def _summarize_stage_errors(errors: List[dict]) -> Dict[str, str]:
    """按阶段提取精简错误摘要。"""
    stage_summary: Dict[str, str] = {}
    for err in errors or []:
        stage = err.get("stage") or "unknown"
        detail = (err.get("stderr") or err.get("stdout") or err.get("message") or "").strip()
        if detail and stage not in stage_summary:
            stage_summary[stage] = detail.splitlines()[0]
    return stage_summary


def _count_manifest_entries(manifest_path: Path) -> int:
    """统计清单文件中非注释条目数量。"""
    if not manifest_path.exists():
        return 0

    count = 0
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
    return count


@dataclass
class DownloadRequest:
    """
    GUI 与后台线程之间的数据载体。
    """

    source_mode: str
    requirements_path: Optional[str]
    packages: List[str]
    python_version: Optional[str]
    output_dir: Optional[str]
    config_path: Optional[str]
    platform: Optional[str]
    implementation: str
    abi: Optional[str]
    only_binary: Optional[str]
    with_hashes: bool
    verbose: bool
    dry_run: bool
    retries: int
    timeout: int


class DownloadWorker(QThread):
    """
    使用 WheelDownloader/RequirementsGenerator 的后台任务。
    """

    log_message = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    started_signal = pyqtSignal()

    def __init__(self, request: DownloadRequest, parent=None) -> None:
        super().__init__(parent)
        self.request = request
        self.output_dir: Optional[str] = None

    def _log(self, message: str) -> None:
        self.log_message.emit(message)

    def run(self) -> None:
        self.started_signal.emit()
        try:
            self._perform()
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"错误：{exc}")
            self.finished.emit(False, str(exc))

    # pylint: disable=too-many-locals
    def _perform(self) -> None:
        req = self.request
        self._log("读取配置与参数...")
        config = Config(config_path=req.config_path)

        python_version = req.python_version or config.get("default_python_version")
        if not python_version:
            raise ValueError("未指定 Python 版本，且配置文件未提供默认值。")
        validate_python_version(python_version)
        python_warning = get_python_version_warning(python_version)
        if python_warning:
            self._log(python_warning)

        output_dir = req.output_dir or config.download_dir
        self.output_dir = output_dir
        platform = req.platform or config.get("default_platform", "auto")
        only_binary = req.only_binary or ":all:"
        command_timeout = max(req.timeout, 60)

        downloader = WheelDownloader(
            python_version=python_version,
            output_dir=output_dir,
            platform=platform if platform != "auto" else None,
            implementation=req.implementation or "cp",
            abi=req.abi,
            only_binary=only_binary,
            verbose=req.verbose,
            config_pip_args=config.get_pip_args(),
            max_attempts=req.retries,
            retry_delay=3.0,
            command_timeout=command_timeout,
        )

        self._log(f"开始下载（Python {python_version}, 平台 {platform}）...")

        resolver = DependencyResolver(
            python_version=python_version,
            platform=platform if platform != "auto" else None,
            pip_args=config.get_pip_args(),
            use_uv=config.use_uv_resolver,
            timeout=req.timeout,
            verbose=req.verbose,
        )
        if req.source_mode == "requirements":
            if not req.requirements_path:
                raise ValueError("未提供 requirements 文件路径。")
            # 保留 -r 原生语义：优先 uv，失败或不可用时直接透传 pip -r
            resolved_packages, used_uv, resolver_warning = resolver.resolve_from_requirements_file(req.requirements_path)
            if resolver_warning:
                self._log(f"解析提示：{resolver_warning}")

            if used_uv and resolved_packages:
                result = downloader.download_resolved_requirements(
                    resolved_packages,
                    dry_run=req.dry_run
                )
            else:
                result = downloader.download_from_requirements(
                    req.requirements_path,
                    dry_run=req.dry_run
                )
        else:
            packages_input = [pkg.strip() for pkg in req.packages if pkg.strip()]
            if not packages_input:
                raise ValueError("未找到需要处理的包，请检查输入")

            resolved_packages, used_uv, resolver_warning = resolver.resolve(packages_input)
            if resolver_warning:
                self._log(f"解析提示：{resolver_warning}")

            if used_uv and resolved_packages:
                result = downloader.download_resolved_requirements(
                    resolved_packages,
                    dry_run=req.dry_run
                )
                if (
                    not req.dry_run
                    and not result.get("success")
                    and WheelDownloader._detect_no_wheel_reason(result.get("errors") or [])
                ):
                    self._log("uv 解析结果下载失败，回退到原始包列表重试。")
                    result = downloader.download_packages(
                        packages_input,
                        dry_run=req.dry_run
                    )
            else:
                result = downloader.download_packages(
                    packages_input,
                    dry_run=req.dry_run
                )

        if not result.get("success"):
            if result.get("fallback_reason"):
                self._log(f"回退原因：{result['fallback_reason']}")
            stage_summary = _summarize_stage_errors(result.get("errors") or [])
            for stage, detail in stage_summary.items():
                self._log(f"[{stage}] {detail}")
            errors = result.get("errors") or []
            for err in errors:
                detail = err.get("stderr") or err.get("stdout") or err.get("message", "")
                if detail:
                    self._log(detail.strip())
            raise RuntimeError(result.get("error", "下载失败"))

        if req.dry_run:
            self._log("模拟运行完成，可在日志中查看命令。")
            self.finished.emit(True, "Dry-run 完成。")
            return

        if result.get("output"):
            self._log(result["output"])
        if result.get("used_source_fallback"):
            self._log("wheel-only 下载失败，已自动回退下载源码包。")
            if result.get("fallback_reason"):
                self._log(f"回退原因：{result['fallback_reason']}")
            self._log("请先按 SOURCE_INSTALL_GUIDE.md 处理源码包，再执行离线安装。")

        generator = RequirementsGenerator(output_dir=output_dir, with_hashes=req.with_hashes)
        self._log("生成离线 requirements 与安装脚本...")
        req_file = generator.generate()
        script_path = generator.generate_install_script()

        wheel_count = len(list(Path(output_dir).glob("*.whl")))
        sources_manifest = Path(output_dir) / "sources-offline.txt"
        source_count = _count_manifest_entries(sources_manifest)

        summary = (
            f"下载完成。离线 requirements：{req_file}，脚本：{script_path}，"
            f"wheels={wheel_count}，源码包={source_count}"
        )
        if source_count > 0:
            self._log("检测到源码包，请先按 SOURCE_INSTALL_GUIDE.md 处理后再执行离线安装脚本。")
            self._log(f"源码包清单：{sources_manifest}")
        self._log(summary)
        self.finished.emit(True, summary)
