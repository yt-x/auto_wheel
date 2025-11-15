"""
主窗口，负责协调表单、日志与后台线程。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QLabel,
    QProgressBar,
    QComboBox,
    QMessageBox,
)

from .forms import ParameterForm
from .theme import available_themes, apply_theme, save_theme_preference
from .workers import DownloadRequest, DownloadWorker


class MainWindow(QMainWindow):
    """
    Auto Wheel GUI 主窗口。
    """

    def __init__(self, initial_theme: str, qt_app, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.qt_app = qt_app
        self.current_theme = initial_theme
        self.worker: Optional[DownloadWorker] = None
        self._last_output_dir: Optional[str] = None

        self.setWindowTitle("Auto Wheel GUI")
        self.resize(1100, 700)

        self._build_ui()

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        self.form = ParameterForm()
        splitter.addWidget(self.form)

        right_panel = QWidget()
        self._build_right_panel(right_panel)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

    def _build_right_panel(self, container: QWidget) -> None:
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.status_label = QLabel("等待任务")
        header.addWidget(self.status_label, stretch=1)

        header.addWidget(QLabel("主题："))
        self.theme_combo = QComboBox()
        for key, label in available_themes():
            self.theme_combo.addItem(label, userData=key)
            if key == self.current_theme:
                self.theme_combo.setCurrentIndex(self.theme_combo.count() - 1)
        self.theme_combo.currentIndexChanged.connect(self._change_theme)
        header.addWidget(self.theme_combo)
        layout.addLayout(header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, stretch=1)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("开始下载")
        self.start_button.clicked.connect(self._handle_start)
        button_row.addWidget(self.start_button)

        self.clear_log_button = QPushButton("清空日志")
        self.clear_log_button.clicked.connect(self.log_view.clear)
        button_row.addWidget(self.clear_log_button)

        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.clicked.connect(self._open_output_dir)
        button_row.addWidget(self.open_output_button)

        layout.addLayout(button_row)

    def _handle_start(self) -> None:
        if self.worker is not None:
            return
        try:
            request = self.form.build_request()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        self.log_view.clear()
        self._set_running(True)
        self.status_label.setText("执行中...")

        self.worker = DownloadWorker(request=request)
        self.worker.log_message.connect(self._append_log)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.started_signal.connect(lambda: self._append_log("任务启动"))
        self.worker.start()

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _on_worker_finished(self, success: bool, message: str) -> None:
        self._set_running(False)
        self.status_label.setText("完成" if success else "失败")
        if self.worker:
            self._last_output_dir = self.worker.output_dir
        QMessageBox.information(self, "任务结果" if success else "任务失败", message)
        self.worker = None

    def _set_running(self, running: bool) -> None:
        self.form.setDisabled(running)
        self.start_button.setDisabled(running)
        if running:
            self.progress_bar.setRange(0, 0)  # 无限加载
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)

    def _change_theme(self) -> None:
        key = self.theme_combo.currentData()
        if not key or key == self.current_theme:
            return
        self.current_theme = key
        apply_theme(self.qt_app, key)
        save_theme_preference(key)

    def _open_output_dir(self) -> None:
        directory = self._last_output_dir
        if not directory:
            QMessageBox.information(self, "提示", "暂无可打开的输出目录。")
            return
        path = Path(directory)
        if not path.exists():
            QMessageBox.warning(self, "提示", "目录不存在，请重新执行下载。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
