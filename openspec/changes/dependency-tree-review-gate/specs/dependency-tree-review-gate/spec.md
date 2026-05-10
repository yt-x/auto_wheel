## ADDED Requirements

### Requirement: 依赖树预览产物
系统 MUST 支持在不执行实际下载的前提下生成依赖树预览产物，至少包含 `dependency-tree.json`、`dependency-tree.txt` 与 `coverage-report.md`，用于下载前审阅与审计。

#### Scenario: CLI 预览模式成功输出
- **GIVEN** 用户通过 CLI 提供 `-r` 或 `-pkg`，并启用预览模式
- **WHEN** 依赖解析流程成功完成
- **THEN** 输出目录 MUST 生成 `dependency-tree.json`、`dependency-tree.txt`、`coverage-report.md`
- **THEN** 预览流程 MUST 不调用实际包下载命令

#### Scenario: GUI 预览模式成功输出
- **GIVEN** 用户在 GUI 启用高级模式并点击“预览依赖树”
- **WHEN** 后台线程解析成功
- **THEN** GUI MUST 展示树摘要与覆盖统计
- **THEN** 输出目录 MUST 写入与 CLI 相同命名的预览文件

### Requirement: 确认闸口执行控制
系统 MUST 支持“确认后下载”执行闸口；当启用高级模式时，未确认依赖树不得执行下载阶段。

#### Scenario: 高级模式未确认时阻断下载
- **GIVEN** 用户启用高级模式且尚未确认依赖树
- **WHEN** 用户尝试执行下载
- **THEN** 系统 MUST 阻断下载并提示先完成依赖树确认

#### Scenario: 高级模式确认后允许下载
- **GIVEN** 用户启用高级模式并已确认当前依赖树
- **WHEN** 用户执行下载
- **THEN** 系统 MUST 进入下载阶段并保留现有离线产物生成行为

### Requirement: 默认流程向后兼容
系统 MUST 保持现有默认下载流程兼容；未启用高级模式时，行为 SHALL 与当前版本一致。

#### Scenario: 旧脚本无新增参数仍可运行
- **GIVEN** 现有 CLI 脚本未使用预览/确认参数
- **WHEN** 用户按旧方式执行下载
- **THEN** 系统 MUST 继续完成下载与离线文件生成
- **THEN** 不得强制要求依赖树确认
