## Context

当前实现的核心链路是：
- CLI：`main.py` 解析参数与配置 -> `resolver.py` 解析 依赖 -> `downloader.py` 下载 -> `requirements_generator.py` 生成离线清单。
- GUI：`workers.py` 复用相同核心逻辑。

问题在于链路语义不一致：
1) `resolver` 已产生锁定依赖列表（尤其在 `uv` 成功时）；
2) 下载阶段通常按该锁定列表执行；
3) 生成 `requirements-offline.txt` 时却改为扫描目录并按包名保留最高版本。

该设计在“目录干净、单次执行”时可工作，但在以下常见场景会失效：
- 输出目录复用导致历史 wheel 残留；
- fallback 后目录中存在多版本混合；
- 依赖约束对次要版本敏感（如 SQLAlchemy 及其生态）。

因此需要将“离线清单来源”从目录推断切换为“解析锁定结果优先”，同时保留非锁定模式兼容。

## Goals / N   on-Goals

**Goals:**
- 让 `requirements-offline.txt` 与解析阶段锁定依赖保持一致，消除版本漂移。
- 在不破坏现有下载与回退机制的前提下，新增“锁定清单与下载产物对账”能力。
- 在无锁定清单时保持兼容路径，但显式标注风险与模式状态。
- 保证 CLI 与 GUI 语义一致，测试可验证。

**Non-Goals:**
- 不重写解析器（uv/pip）或替换下载引擎。
- 不在本次变更中引入新的包管理后端。
- 不承诺在非锁定模式下完全消除历史目录污染风险（仅提升可见性与警示）。

## Decisions

### 决策 1：离线清单采用“锁定优先、扫描兜底”
- 方案：`RequirementsGenerator.generate()` 增加可选输入 `resolved_requirements`（锁定清单）。存在时直接以其写入 `requirements-offline.txt`；不存在时回退到目录扫描逻辑。
- 理由：锁定清单是解析阶段已验证的语义，能够避免目录推断偏差。
- 替代方案：始终扫描目录。
  - 放弃原因：无法防止残留文件造成版本漂移。

### 决策 2：保留现有目录扫描逻辑，但降级为“兼容模式”
- 方案：目录扫描不删除，作为 `resolved_requirements is None` 的兼容路径；并输出 `manifest_mode=non_lock` 警示。
- 理由：当前 `-r` 在 uv 不可用时仍需可用路径，不能强制依赖锁定解析。
- 替代方案：无锁定清单即失败。
  - 放弃原因：会破坏现有可用性与用户预期。

### 决策 3：新增“锁定-产物对账”报告
- 方案：下载完成后生成对账结果，至少包含：`missing_from_artifacts`、`source_only`、`extra_artifacts_not_in_lock`、`manifest_mode`。
- 理由：锁定驱动能解决主要冲突，但对账能提前暴露下载差异和目录污染。
- 替代方案：仅日志提示。
  - 放弃原因：不可审计、难测试、GUI/CLI 不易一致展示。

### 决策 4：下载逻辑保持不变，风险集中到清单生成层修复
- 方案：不改 `WheelDownloader` 的 wheel/source fallback 与重试机制，仅调整清单来源和结果验证。
- 理由：将变更范围最小化，降低引入旧问题概率。
- 替代方案：同时重构下载命令策略（如强制 `--no-deps`）。
  - 放弃原因：风险较高，容易影响当前已有兼容行为。

## Risks / Trade-offs

- [风险] 锁定清单中包含 marker/extras 复杂表达式，直接落盘可能与当前“文件名反推”语义不同。
  - 缓解：在对账报告中增加规范化字段（包名+版本）并补充测试样本。
- [风险] 非锁定模式仍可能受目录残留影响。
  - 缓解：显式标注 `manifest_mode=non_lock`，并建议使用独立输出目录。
- [风险] CLI 与 GUI 若改造不同步会造成语义分叉。
  - 缓解：共享同一 `RequirementsGenerator` 接口，测试覆盖双入口。
- [风险] 新报告文件增加用户理解成本。
  - 缓解：默认输出摘要并在详细报告中给出解释，不改变基础操作路径。

## Migration Plan

1. 扩展 `RequirementsGenerator` 接口，支持锁定清单输入与模式标识输出。
2. 在 `main.py` 与 `gui/workers.py` 统一传递 `resolved_packages`（若存在）给生成器。
3. 增加并输出对账报告（JSON/MD 至少一种机器可读 + 一种人类可读）。
4. 补充单元测试与回归测试：锁定优先、非锁定兼容、残留文件污染防护验证。
5. 更新 README/QUICKSTART 中“锁定模式/非锁定模式”说明。

## Open Questions

- 对账报告文件名是否复用 `coverage-report.md`，还是新增独立文件（建议新增，避免语义混淆）。
- 非锁定模式是否在 CLI 返回非零退出码（建议不改变退出码，仅强提示）。
- 是否需要增加可选参数显式控制（如 `--manifest-mode lock|scan|auto`），还是先采用自动策略。
