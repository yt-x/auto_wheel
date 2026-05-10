## Why

当前代码链路在 `resolver -> downloader` 阶段已经拿到了目标环境的锁定依赖（pinned requirements），但 `requirements-offline.txt` 的生成改为“扫描输出目录并按包名取最高版本”。在复用输出目录、回退下载或历史残留文件存在时，这会引入锁定结果之外的版本，导致离线安装出现冲突（如 `sqlalchemy==2.0.49` 与其他依赖约束不一致）。

## What Changes

- 引入“锁定清单驱动离线清单（lock-driven manifest）”策略：当解析阶段产出锁定依赖时，`requirements-offline.txt` MUST 直接由该锁定清单生成，不再通过目录扫描推断版本。
- 保留现有下载流程与回退机制（wheel-only -> source fallback），但新增“下载结果与锁定清单对账”产物，明确缺失项、仅源码项、额外项。
- 保留非锁定模式兼容路径：当未产生锁定清单（例如 uv 不可用并走 pip 原始语义）时，继续使用目录扫描生成清单，并在报告中显式标注“非锁定模式”。
- CLI 与 GUI 统一接入上述语义，保证两入口输出一致的状态与风险提示。
- 增加回归测试：覆盖锁定清单优先、历史残留不污染离线清单、非锁定模式兼容三类场景。

## Capabilities

### New Capabilities
- `lock-driven-offline-manifest`: 离线安装清单由解析阶段锁定依赖直接生成，避免目录扫描引入版本漂移。
- `download-lock-reconciliation`: 下载完成后对“锁定依赖 vs 实际产物”做一致性对账并输出机器可读/人类可读报告。
- `non-lock-mode-manifest-compatibility`: 在无锁定清单场景保留现有目录扫描行为并强制输出风险标识，确保向后兼容。

### Modified Capabilities
- （无）

## Impact

- 影响代码：`src/auto_wheel/main.py`、`src/auto_wheel/gui/workers.py`、`src/auto_wheel/requirements_generator.py`，以及对应测试文件。
- 对离线安装流程影响：默认仍生成 `requirements-offline.txt` 与安装脚本；差异在于优先依据锁定清单生成，减少冲突。
- 回退机制兼容性：保留现有 wheel/source 回退行为，不改变下载阶段核心策略，只改变离线清单来源优先级与对账方式。
- 入口影响：CLI 与 GUI 均受影响，且必须保持一致语义。
