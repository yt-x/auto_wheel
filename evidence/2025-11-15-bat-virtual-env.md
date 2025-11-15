# 任务记录：BAT 虚拟环境安装修复
- **时间**：2025-11-15
- **目标**：确保自动生成的离线安装脚本在 Windows/Linux 下优先使用项目虚拟环境或指定 Python 解释器，避免全局安装。
- **关键动作**：
  1. 调整 `RequirementsGenerator.generate_install_script` 生成的 `install.sh` 与 `install.bat`，自动解析 `VIRTUAL_ENV` / `CONDA_PREFIX`，并回退到系统 `python`，始终执行 `python -m pip`。
  2. 为脚本添加中文提示及错误处理，确保找不到 Python 时立即终止并提示激活虚拟环境。
  3. 将运行结果与注意事项记录于当前文件，满足 evidence 追踪要求。
- **验证**：手动审查脚本内容，确认变量引用与路径均加引号，Windows 分支覆盖 `py.exe`/`python.exe`，Unix 分支使用 `set -euo pipefail` 并在找不到解释器时退出。
- **风险 & 后续**：脚本假设离线环境至少安装了某个 Python 发行版；如需自动创建虚拟环境，可在未来扩展。当前变更为破坏性更新，“无迁移，直接替换”。
