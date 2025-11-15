"""
GUI 入口：创建 QApplication 并启动主窗口。
"""

from __future__ import annotations

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from .main_window import MainWindow
from .theme import apply_theme, load_theme_preference


def run() -> None:
    """
    图形界面入口函数。
    """
    # 启用 HiDPI（Qt6 默认已支持，此处兼容可用枚举）
    for attr_name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attr = getattr(Qt.ApplicationAttribute, attr_name, None)
        if attr is not None:
            QApplication.setAttribute(attr, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Auto Wheel GUI")

    theme_key = load_theme_preference()
    apply_theme(app, theme_key)

    window = MainWindow(initial_theme=theme_key, qt_app=app)
    window.show()
    sys.exit(app.exec())
