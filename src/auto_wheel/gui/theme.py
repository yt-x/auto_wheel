"""
主题管理，负责 qt-material 皮肤加载与偏好持久化。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Tuple

THEME_CONFIG_PATH = Path.home() / ".auto_wheel_gui.json"
THEME_KEY = "theme"

THEME_CATALOG: Dict[str, Dict[str, str]] = {
    "light": {"label": "亮色模式", "material": "light_blue.xml"},
    "dark": {"label": "暗色模式", "material": "dark_teal.xml"},
}

DEFAULT_THEME_KEY = "light"


def available_themes() -> Iterable[Tuple[str, str]]:
    """
    返回所有可选主题 (key, label)。
    """
    for key, meta in THEME_CATALOG.items():
        yield key, meta["label"]


def load_theme_preference() -> str:
    """
    读取用户主题偏好，默认亮色。
    """
    if THEME_CONFIG_PATH.exists():
        try:
            data = json.loads(THEME_CONFIG_PATH.read_text(encoding="utf-8"))
            key = data.get(THEME_KEY)
            if key in THEME_CATALOG:
                return key
        except json.JSONDecodeError:
            pass
    return DEFAULT_THEME_KEY


def save_theme_preference(theme_key: str) -> None:
    """
    保存用户主题偏好。
    """
    if theme_key not in THEME_CATALOG:
        return
    payload = {THEME_KEY: theme_key}
    try:
        THEME_CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def apply_theme(app, theme_key: str) -> None:
    """
    对 QApplication 应用指定主题，若 qt-material 缺失则静默忽略。
    """
    theme = THEME_CATALOG.get(theme_key, THEME_CATALOG[DEFAULT_THEME_KEY])["material"]
    try:
        from qt_material import apply_stylesheet

        apply_stylesheet(app, theme=theme, invert_secondary=True)
    except Exception:
        # 如果 qt-material 未安装或应用失败，则维持 Qt 默认主题
        pass
