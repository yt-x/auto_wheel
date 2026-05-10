## ADDED Requirements

### Requirement: 任务级状态机
系统 MUST 实现统一任务级状态机，并在 CLI、GUI、报告文件中保持一致状态语义。

#### Scenario: 任务状态按阶段推进
- **GIVEN** 用户启动一次高级模式下载任务
- **WHEN** 任务按“解析 -> 预览确认 -> 下载 -> 预演”推进
- **THEN** 任务状态 MUST 按定义状态迁移，不得出现跳跃或回退到非法状态
- **THEN** 每次状态迁移 MUST 记录时间戳与触发原因

#### Scenario: 任务失败状态终止
- **GIVEN** 任一关键阶段发生不可恢复错误
- **WHEN** 系统判定任务失败
- **THEN** 任务状态 MUST 进入 `failed`
- **THEN** 系统 MUST 输出失败阶段与建议动作

### Requirement: 依赖级状态机
系统 MUST 对每个依赖维护独立状态，并在覆盖报告中可追踪状态迁移。

#### Scenario: 依赖从解析到可用
- **GIVEN** 某依赖在目标环境存在可用 wheel
- **WHEN** 系统完成解析和下载
- **THEN** 该依赖状态 MUST 至少经历 `pending -> resolved -> wheel_ready`
- **THEN** 覆盖报告 MUST 展示最终状态与关键证据

#### Scenario: 依赖进入人工处理状态
- **GIVEN** 某依赖无可用 wheel 且源码采集后仍存在构建风险
- **WHEN** 系统完成自动处理
- **THEN** 该依赖状态 MUST 进入 `manual_required` 或 `unresolved`
- **THEN** 报告 MUST 给出对应处理建议

### Requirement: 产物级状态机
系统 MUST 对关键产物维护状态，并支持校验结果映射。

#### Scenario: 报告产物生成与校验
- **GIVEN** 任务正常完成
- **WHEN** 系统生成依赖树、覆盖报告、可安装性报告
- **THEN** 产物状态 MUST 从 `missing` 迁移到 `generated`
- **THEN** 校验通过后 MUST 迁移到 `validated`

#### Scenario: 产物校验失败
- **GIVEN** 某报告文件生成后格式或内容校验失败
- **WHEN** 系统执行产物校验
- **THEN** 该产物状态 MUST 标记为 `invalid`
- **THEN** 任务总状态 MUST 进入 `completed_with_risks` 或 `failed`
