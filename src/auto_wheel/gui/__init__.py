"""
GUI 子模块，提供 auto-wheel 图形界面入口。
"""

def run():
    """延迟导入 GUI 入口，避免非 GUI 场景硬依赖 PyQt6。"""
    from .app import run as _run
    return _run()

__all__ = ["run"]
