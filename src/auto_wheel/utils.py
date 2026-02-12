"""
共享工具函数模块
"""

from typing import List


def load_requirements(path: str) -> List[str]:
    """
    从文件加载依赖行，忽略注释和空行

    Args:
        path: requirements.txt 文件路径

    Returns:
        清理后的依赖行列表
    """
    lines: List[str] = []
    with open(path, "r", encoding="utf-8") as file_obj:
        for raw_line in file_obj:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            lines.append(line)
    return lines
