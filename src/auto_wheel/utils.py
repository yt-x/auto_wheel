"""
共享工具函数模块
"""

from typing import List, Optional, Tuple


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


def parse_python_version(version: str) -> Tuple[int, int]:
    """
    解析并校验 Python 版本号（X.Y 或 X.Y.Z）。

    Args:
        version: 版本字符串

    Returns:
        (major, minor)

    Raises:
        ValueError: 版本格式不合法
    """
    parts = version.split(".")
    if len(parts) < 2:
        raise ValueError(
            f"Python 版本格式无效: {version}。期望格式: X.Y 或 X.Y.Z（例如 3.9 或 3.9.7）"
        )

    try:
        major, minor = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(
            f"Python 版本无效: {version}。版本号必须是整数。"
        ) from exc

    return major, minor


def validate_python_version(version: str) -> None:
    """
    校验 Python 版本格式，非法时抛出 ValueError。
    """
    parse_python_version(version)


def get_python_version_warning(version: str) -> Optional[str]:
    """
    返回旧版本 Python 的告警文案，若无告警返回 None。
    """
    major, minor = parse_python_version(version)
    if major < 3 or (major == 3 and minor < 7):
        return (
            f"Warning: Python {version} is quite old. "
            "Some packages may not be available."
        )
    return None
