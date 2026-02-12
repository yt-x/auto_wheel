#!/bin/bash
# 离线安装脚本（优先使用当前虚拟环境）
# 由 auto-wheel 自动生成

set -euo pipefail

REQ_FILE="requirements-offline.txt"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
elif [[ -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
    PYTHON_BIN="${CONDA_PREFIX}/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    echo "未找到可用的 Python 解释器，请先激活虚拟环境或将 python 加入 PATH。" >&2
    exit 1
fi

echo "使用 Python: $PYTHON_BIN"
"$PYTHON_BIN" -m pip install --no-index --find-links=. -r "$REQ_FILE"

echo "安装完成！"
