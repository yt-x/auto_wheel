## Status

本变更已并入主变更 `offline-dependency-bundle-completeness`，请以主变更为准执行与验收。

## Why

当前工具在“跨平台/跨架构依赖解析 + wheel 不可用回退”场景下存在可见性不足：用户无法在下载前确认完整依赖树与覆盖状态，且源码回退会放宽目标约束，可能引入与目标环境不一致的产物。  
这会导致“部分包覆盖不到”或“下载成功但离线安装失败”的后置风险，因此需要将依赖树确认前置，并把回退行为约束到可审计边界。

## What Changes

- 新增“解析预览阶段”（不下载）：输出依赖树与覆盖报告，供高级用户确认后再执行下载。
- 新增“确认执行阶段”：CLI/GUI 支持在确认依赖树后继续下载，默认流程保持兼容。
- 增强平台/架构映射精度：将解析平台从粗粒度（linux/windows/macos）提升为可区分架构与 ABI 的目标。
- 收敛源码回退边界：回退阶段仅允许补拉源码包，不引入主机平台 wheel 污染。
- 增加可追溯工件：生成 `dependency-tree.json`、`dependency-tree.txt`、`coverage-report.md`，用于离线交付前审计。

## Capabilities

### New Capabilities
- `dependency-tree-review-gate`: 在下载前生成依赖树与覆盖报告，并提供确认闸口（高级模式）后再执行下载。
- `target-platform-coverage-control`: 对解析/下载/回退流程施加一致的目标平台约束，防止跨平台污染并输出覆盖率状态。

### Modified Capabilities
- 无（当前仓库尚无已发布 OpenSpec capabilities）。

## Impact

- 影响代码：
  - CLI：`src/auto_wheel/cli.py`, `src/auto_wheel/main.py`
  - 解析器：`src/auto_wheel/resolver.py`
  - 下载器：`src/auto_wheel/downloader.py`
  - GUI：`src/auto_wheel/gui/forms.py`, `src/auto_wheel/gui/workers.py`, `src/auto_wheel/gui/main_window.py`
  - 报告生成：`src/auto_wheel/requirements_generator.py`（扩展为树/覆盖报告输出）
  - 测试：`tests/` 新增解析与回退约束测试
- 对离线安装流程影响：
  - 新增“下载前确认”可选步骤；默认不强制，保持现有用户脚本可运行。
  - 新增覆盖报告用于提前识别需源码构建的依赖，降低离线安装失败率。
- 回退兼容性：
  - 仍保留“无可用 wheel 时自动回退”能力，但限制为“仅补拉源码包”并给出阶段化原因。
- 入口影响：
  - CLI 与 GUI 两个入口均受影响；GUI 仅增加预览与确认交互，不改变现有基础下载能力。
