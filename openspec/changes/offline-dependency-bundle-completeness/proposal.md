## Why

当前工具采用 `uv` 优先解析、异常回退 `pip` 的方向是正确的，但在老旧/历史包场景仍存在覆盖盲区：用户常在下载结束后才发现依赖不完整或目标环境不可安装。  
为了实现“在公网一键准备完整离线依赖包，并可在私网稳定安装”的目标，需要把覆盖评估、回退策略和可安装性验证做成一条可审计闭环流程。

本提案同时并入已有 `dependency-tree-review-gate` 变更中的能力，统一形成一个主变更，避免重复实现与重复验收。

## What Changes

- 保持 `uv` 为默认解析器，新增“失败分类”机制，区分“工具执行异常”与“依赖天然不可满足”。
- 增加依赖覆盖评估能力：在下载前后输出依赖树、覆盖状态、风险摘要，明确哪些包需要源码处理或人工介入。
- 新增“依赖树确认闸口”：高级模式下先预览再下载，未确认不得执行下载。
- 增强目标平台控制：平台/架构映射与回退阶段约束保持一致，防止主机平台污染目标产物。
- 增强老旧库兜底采集能力：在 wheel 不可用时，提供对老旧 sdist 的稳健抓取路径，降低受本机构建环境影响的失败率。
- 增加离线可安装性验证能力：在联网端执行“模拟私网安装”校验，提前暴露私网落地风险。
- 增加统一状态模型：明确任务级、依赖级、产物级状态集合与状态迁移，确保 CLI/GUI/报告一致。
- 同步升级 CLI 与 GUI：CLI 增加高级参数与报告输出；GUI 增加覆盖视图、确认闸口与失败指引。

## Capabilities

### New Capabilities
- `dependency-tree-review-gate`: 在下载前生成依赖树预览并提供确认闸口，兼容基础模式。
- `target-platform-coverage-control`: 对平台/架构映射、回退约束和异常路径进行统一控制与审计。
- `dependency-coverage-reporting`: 生成依赖树与覆盖报告，按目标 Python/平台标注 `wheel-ready`、`source-required`、`unresolved`。
- `legacy-package-resilient-fetch`: 面向老旧/历史包的多路径采集机制，避免仅依赖 pip 构建元数据路径导致失败。
- `offline-bundle-installability-check`: 在公网端对离线包执行安装可行性检查，输出私网使用前的通过/失败证据。
- `execution-state-model`: 定义并落地任务级/依赖级/产物级状态机，保证状态可追溯且可测试。

### Modified Capabilities
- 无（当前仓库尚无已发布 OpenSpec capabilities）。

## Impact

- 影响代码：
  - 解析与下载链路：`src/auto_wheel/resolver.py`, `src/auto_wheel/downloader.py`
  - 产物与报告：`src/auto_wheel/requirements_generator.py`
  - CLI：`src/auto_wheel/cli.py`, `src/auto_wheel/main.py`
  - GUI：`src/auto_wheel/gui/forms.py`, `src/auto_wheel/gui/workers.py`, `src/auto_wheel/gui/main_window.py`
  - 测试：`tests/` 增加老旧库样本、失败分类、离线可安装性校验测试
- 对离线安装流程影响：
  - 新增“覆盖报告与可安装性校验”步骤，默认可选，不破坏现有快速流程。
  - 产物中新增覆盖状态与风险提示文件，私网侧可直接使用。
- 回退机制兼容性：
  - 保留当前“失败回退”思路，但改为可分类、可审计、可控的回退分支，避免误把不可满足问题当成可自动修复问题。
- 状态一致性影响：
  - CLI 日志、GUI 展示、报告文件统一复用同一状态模型，避免同一任务在不同界面出现状态歧义。
- 入口影响：
  - CLI 和 GUI 均受影响；基础模式保持兼容，高级模式提供完整闭环体验。
