## ADDED Requirements

### Requirement: 目标平台精确映射
系统 MUST 将用户输入的平台标识映射为可区分操作系统与架构的目标平台语义，并在解析、覆盖报告、下载阶段保持一致。

#### Scenario: Linux x86_64 与 aarch64 区分映射
- **GIVEN** 用户分别指定 `manylinux2014_x86_64` 与 `manylinux2014_aarch64`
- **WHEN** 系统执行依赖解析
- **THEN** 两次解析 MUST 使用不同的目标平台值
- **THEN** 覆盖报告 MUST 反映对应架构差异

#### Scenario: Windows 目标平台映射
- **GIVEN** 用户指定 `win_amd64`
- **WHEN** 系统执行依赖解析
- **THEN** 解析器 MUST 采用对应的 Windows 目标平台语义
- **THEN** 覆盖报告 MUST 标注该平台的可用性结论

### Requirement: 回退阶段防污染约束
当 wheel-only 失败并触发回退时，系统 MUST 仅补拉源码包或显式报告无法自动补齐，不得通过放宽目标约束下载主机平台 wheel。

#### Scenario: 无可用 wheel 时仅回退源码包
- **GIVEN** 目标平台下某依赖不存在可用 wheel
- **WHEN** wheel-only 阶段失败并进入回退
- **THEN** 系统 MUST 不下载与目标平台无关的 wheel
- **THEN** 系统 MUST 在覆盖报告中标注该依赖为 `source-required` 或 `unresolved`

#### Scenario: 回退后仍失败时输出阶段化证据
- **GIVEN** wheel-only 与回退阶段均失败
- **WHEN** 系统返回失败结果
- **THEN** 返回信息 MUST 包含阶段化失败摘要（至少包含 `wheel_only` 与 `source_fallback`）
- **THEN** 覆盖报告 MUST 记录失败原因摘要

### Requirement: 异常路径可观察性
系统 MUST 对关键异常路径给出可审计反馈，并在 CLI/GUI 上保持一致语义。

#### Scenario: 网络超时
- **GIVEN** 下载或解析过程中发生网络超时
- **WHEN** 系统捕获超时异常
- **THEN** 系统 MUST 输出超时阶段、重试次数与最终状态
- **THEN** 不得误判为“无可用 wheel”

#### Scenario: pip 不可用
- **GIVEN** 运行环境中 pip 子进程无法启动
- **WHEN** 系统尝试执行下载命令
- **THEN** 系统 MUST 返回可读错误并终止当前流程
- **THEN** GUI 与 CLI MUST 给出一致的错误语义
