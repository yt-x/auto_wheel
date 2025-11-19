"""
后台线程：执行下载与离线脚本生成。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from ..config import Config
from ..downloader import WheelDownloader
from ..requirements_generator import RequirementsGenerator
from ..resolver import DependencyResolver
from ..resolver import DependencyResolver


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

        # 准备包列表
        if req.source_mode == "requirements":
            packages_input = self._load_requirements(req.requirements_path)
        else:
            packages_input = [pkg.strip() for pkg in req.packages if pkg.strip()]

        if not packages_input:
            raise ValueError("未找到需要处理的包，请检查输入")

        resolver = DependencyResolver(
            python_version=python_version,
            platform=platform if platform != "auto" else None,
            pip_args=config.get_pip_args(),
            use_uv=config.use_uv_resolver,
            timeout=req.timeout,
            verbose=req.verbose,
        )
        resolved_packages, used_uv, resolver_warning = resolver.resolve(packages_input)
        if resolver_warning:
            self._log(f"解析提示：{resolver_warning}")

        if req.dry_run:
            # 仅打印命令
            result = downloader.download_resolved_requirements(resolved_packages, dry_run=True)
        else:
            result = downloader.download_resolved_requirements(resolved_packages, dry_run=False)

        if not result.get("success"):
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

        generator = RequirementsGenerator(output_dir=output_dir, with_hashes=req.with_hashes)
        self._log("生成离线 requirements 与安装脚本...")
        req_file = generator.generate()
        script_path = generator.generate_install_script()

        summary = f"下载完成。离线 requirements：{req_file}，脚本：{script_path}"
        self._log(summary)
        self.finished.emit(True, summary)

    @staticmethod
    def _load_requirements(path: str) -> List[str]:
        lines: List[str] = []
        with open(path, "r", encoding="utf-8") as file_obj:
            for raw_line in file_obj:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                lines.append(line)
        return lines
