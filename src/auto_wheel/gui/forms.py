"""
参数表单，负责在 GUI 中收集下载所需信息。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QHBoxLayout,
    QRadioButton,
    QButtonGroup,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QPlainTextEdit,
    QLabel,
    QCheckBox,
    QSpinBox,
    QFormLayout,
)

from ..utils import validate_python_version
from .workers import DownloadRequest


@dataclass
class FormState:
    """
    用于中间状态保存的结构。
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


class ParameterForm(QWidget):
    """
    图形化参数表单。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_source_group())
        layout.addWidget(self._build_paths_group())
        layout.addWidget(self._build_options_group())
        layout.addStretch(1)

    def _build_source_group(self) -> QGroupBox:
        group = QGroupBox("依赖来源")
        vbox = QVBoxLayout(group)

        self.requirements_radio = QRadioButton("使用 requirements.txt")
        self.packages_radio = QRadioButton("指定包列表")
        self.requirements_radio.setChecked(True)

        radio_group = QButtonGroup(group)
        radio_group.addButton(self.requirements_radio)
        radio_group.addButton(self.packages_radio)

        vbox.addWidget(self.requirements_radio)
        self.requirements_path_edit = QLineEdit()
        self.requirements_path_edit.setPlaceholderText("例如：C:/path/to/requirements.txt")
        req_row = QHBoxLayout()
        req_row.addWidget(self.requirements_path_edit, stretch=1)
        browse_req_btn = QPushButton("浏览")
        browse_req_btn.clicked.connect(self._choose_requirements_file)
        req_row.addWidget(browse_req_btn)
        vbox.addLayout(req_row)

        vbox.addSpacing(8)
        vbox.addWidget(self.packages_radio)
        self.packages_edit = QPlainTextEdit()
        self.packages_edit.setPlaceholderText("每行一个包，例如：\nrequests==2.31.0\nflask")
        self.packages_edit.setEnabled(False)
        vbox.addWidget(self.packages_edit)

        self.requirements_radio.toggled.connect(self._toggle_source_inputs)

        return group

    def _build_paths_group(self) -> QGroupBox:
        group = QGroupBox("路径与版本")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.python_version_edit = QLineEdit()
        self.python_version_edit.setPlaceholderText("例如：3.9（留空将读取配置文件）")
        form.addRow("Python 版本：", self.python_version_edit)

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("默认：配置文件 download_dir 或 ./downloads")
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir_edit, stretch=1)
        output_btn = QPushButton("选择目录")
        output_btn.clicked.connect(self._choose_output_dir)
        output_row.addWidget(output_btn)
        form.addRow("输出目录：", output_row)

        self.config_path_edit = QLineEdit()
        self.config_path_edit.setPlaceholderText("可选：config.json 路径")
        config_row = QHBoxLayout()
        config_row.addWidget(self.config_path_edit, stretch=1)
        config_btn = QPushButton("浏览")
        config_btn.clicked.connect(self._choose_config_file)
        config_row.addWidget(config_btn)
        form.addRow("配置文件：", config_row)

        self.platform_edit = QLineEdit()
        self.platform_edit.setPlaceholderText("例如：manylinux2014_x86_64，留空表示 auto")
        form.addRow("目标平台：", self.platform_edit)

        self.implementation_edit = QLineEdit("cp")
        form.addRow("Python 实现：", self.implementation_edit)

        self.abi_edit = QLineEdit()
        self.abi_edit.setPlaceholderText("例如：cp39，留空自动推断")
        form.addRow("ABI 标签：", self.abi_edit)

        self.only_binary_edit = QLineEdit(":all:")
        form.addRow("only-binary：", self.only_binary_edit)

        return group

    def _build_options_group(self) -> QGroupBox:
        group = QGroupBox("高级选项")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.with_hashes_check = QCheckBox("生成带哈希的 requirements")
        form.addRow(self.with_hashes_check)

        self.verbose_check = QCheckBox("显示 pip 详细输出")
        form.addRow(self.verbose_check)

        self.dry_run_check = QCheckBox("仅模拟（不下载）")
        form.addRow(self.dry_run_check)

        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 10)
        self.retries_spin.setValue(3)
        form.addRow("最大重试次数：", self.retries_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(60, 1800)
        self.timeout_spin.setValue(300)
        form.addRow("命令超时（秒）：", self.timeout_spin)

        return group

    def _choose_requirements_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 requirements.txt", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            self.requirements_path_edit.setText(file_path)

    def _choose_config_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 config.json", "", "JSON Files (*.json);;All Files (*)")
        if file_path:
            self.config_path_edit.setText(file_path)

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if directory:
            self.output_dir_edit.setText(directory)

    def _toggle_source_inputs(self, checked: bool) -> None:
        """
        根据选择启用/禁用输入。
        """
        use_requirements = checked
        self.requirements_path_edit.setEnabled(use_requirements)
        self.packages_edit.setEnabled(not use_requirements)

    def collect_state(self) -> FormState:
        """
        将当前 UI 值转换为结构化数据。
        """
        source_mode = "requirements" if self.requirements_radio.isChecked() else "packages"
        req_path = self.requirements_path_edit.text().strip() or None
        packages = [line.strip() for line in self.packages_edit.toPlainText().splitlines() if line.strip()]

        python_version = self.python_version_edit.text().strip() or None
        if python_version:
            validate_python_version(python_version)

        output_dir = self.output_dir_edit.text().strip() or None
        config_path = self.config_path_edit.text().strip() or None
        platform = self.platform_edit.text().strip() or None
        implementation = self.implementation_edit.text().strip() or "cp"
        abi = self.abi_edit.text().strip() or None
        only_binary = self.only_binary_edit.text().strip() or None

        return FormState(
            source_mode=source_mode,
            requirements_path=req_path,
            packages=packages,
            python_version=python_version,
            output_dir=output_dir,
            config_path=config_path,
            platform=platform,
            implementation=implementation,
            abi=abi,
            only_binary=only_binary,
            with_hashes=self.with_hashes_check.isChecked(),
            verbose=self.verbose_check.isChecked(),
            dry_run=self.dry_run_check.isChecked(),
            retries=self.retries_spin.value(),
            timeout=self.timeout_spin.value(),
        )

    def build_request(self) -> DownloadRequest:
        """
        生成 DownloadRequest，若输入不完整则抛出 ValueError。
        """
        state = self.collect_state()

        if state.source_mode == "requirements":
            if not state.requirements_path:
                raise ValueError("请指定 requirements.txt 路径。")
            if not Path(state.requirements_path).exists():
                raise ValueError("指定的 requirements 文件不存在。")
        else:
            if not state.packages:
                raise ValueError("请至少输入一个包名。")

        return DownloadRequest(
            source_mode=state.source_mode,
            requirements_path=state.requirements_path,
            packages=state.packages,
            python_version=state.python_version,
            output_dir=state.output_dir,
            config_path=state.config_path,
            platform=state.platform,
            implementation=state.implementation,
            abi=state.abi,
            only_binary=state.only_binary,
            with_hashes=state.with_hashes,
            verbose=state.verbose,
            dry_run=state.dry_run,
            retries=state.retries,
            timeout=state.timeout,
        )
