# 任务记录：目录整理与文档更新
- **时间**：2025-11-15
- **目标**：根据 GUI 落地后的反馈，清理无用/冗余文件并统一示例资源位置，同时更新文档说明。
- **动作**：
  1. 删除过时的 `requirements.txt`（早期 PyQt5 依赖）与 `plan.md`，防止与现有 pyproject 配置冲突。
  2. 新增 `examples/` 目录，迁移 `config.example.json` 与 `example_requirements.txt`，并在 README/QUICKSTART/TECHNICAL_OVERVIEW 中更新引用路径。
  3. README 在配置章节注明参考示例文件，QUICKSTART/TECHNICAL_OVERVIEW 所有示例命令均改用 `examples/example_requirements.txt`。
- **验证**：手动审查目录 (`ls`) 确认根目录仅保留必要文件；`compileall` 已在上一阶段覆盖 GUI 代码，当前变更仅涉及文档与静态资源，无需额外运行。
- **说明**：示例文件移动后，命令需显式使用 `examples/` 路径；CLI/GUI 逻辑未改动。
