# 任务记录：下载稳健性与技术文档更新
- **时间**：2025-11-15
- **目标**：
  1. 清理 `requirements_generator.py`、`downloader.py` 未使用的导入，确保日志输出聚焦有效信息。
  2. 为 `WheelDownloader` 增加命令级重试、超时与线性退避，避免网络抖动导致整体失败。
  3. 产出最新《TECHNICAL_OVERVIEW》文档并在 README 链接，方便开发者理解架构与脚本行为。
- **关键实现**：
  - `WheelDownloader` 现支持 `max_attempts`（默认读取配置 `retries`）、`retry_delay`、`command_timeout`，对 `TimeoutExpired`/`CalledProcessError`/`OSError` 分类型记录并线性 backoff。
  - `install.sh`/`install.bat` 逻辑已记录在 `docs/TECHNICAL_OVERVIEW.md`，README 新增引用。
  - `requirements_generator.py` 去除 `subprocess`、`sys` 等死代码导入。
- **验证**：
  - `.venv\\Scripts\\python.exe -m py_compile src/auto_wheel/downloader.py src/auto_wheel/requirements_generator.py src/auto_wheel/main.py`
  - `.venv\\Scripts\\python.exe -m auto_wheel.main --help`
- **后续**：若需可配置的 `retry_delay` 或更细粒度日志，可在 `config.json` 中新增字段并透传至 `WheelDownloader`；当前版本为“无迁移，直接替换”。
