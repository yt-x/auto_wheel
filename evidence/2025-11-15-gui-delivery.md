# 任务记录：PyQt6 GUI 实现
- **时间**：2025-11-15
- **目标**：为 auto-wheel 提供独立 GUI，纯代码构建界面、集成 qt-material，并在不影响 CLI 的前提下复用现有下载/脚本逻辑。
- **核心变更**：
  1. `pyproject.toml` 新增 `[project.optional-dependencies.gui]`（PyQt6、qt-material）及 `auto-wheel-gui` 启动脚本。
  2. 新增 `src/auto_wheel/gui/`：包含 `app.py`（入口）、`main_window.py`（界面逻辑）、`forms.py`（参数表单）、`workers.py`（后台线程）、`theme.py`（主题管理）及 `__init__.py`。
  3. README/TECHNICAL_OVERVIEW 更新 GUI 使用说明与架构描述。
- **功能概览**：
  - 表单支持 requirements / 包列表两种来源，含 Python 版本、平台、镜像等配置项。
  - 后台线程复用 `WheelDownloader` 与 `RequirementsGenerator`，日志与结果实时反馈。
  - `qt-material` 支持亮/暗主题切换并持久化偏好。
- **验证**：`.venv\Scripts\python.exe -c "import compileall, pathlib; ..."` 逐个编译核心模块，确认语法与依赖声明无误（GUI 运行需安装 `[gui]` 额外依赖）。
- **说明**：GUI 仅作为包装层，与 CLI 完全解耦，如需使用请执行 `pip install -e .[gui] && auto-wheel-gui`。无迁移，直接新增。
