## ADDED Requirements

### Requirement: 离线包可安装性预演
系统 MUST 支持在联网端对已下载离线包执行“模拟私网安装”预演，并生成可审计结果。

#### Scenario: 预演通过
- **GIVEN** 下载目录包含完整离线依赖与 requirements 文件
- **WHEN** 用户启用可安装性预演
- **THEN** 系统 MUST 在隔离环境执行 `--no-index --find-links` 安装验证
- **THEN** 系统 MUST 生成 `installability-report.md` 并标记为通过

#### Scenario: 预演失败
- **GIVEN** 下载目录存在缺失依赖或不可构建源码包
- **WHEN** 系统执行可安装性预演
- **THEN** 系统 MUST 标记预演失败并输出失败包清单
- **THEN** 报告 MUST 提供下一步操作建议

### Requirement: CLI 与 GUI 一致可见性
系统 MUST 在 CLI 与 GUI 两个入口提供一致的预演结果展示语义。

#### Scenario: CLI 输出预演摘要
- **GIVEN** 用户通过 CLI 触发预演
- **WHEN** 预演完成
- **THEN** CLI MUST 输出通过/失败摘要与报告路径
- **THEN** CLI MUST 在失败时返回非零退出码

#### Scenario: GUI 输出预演摘要
- **GIVEN** 用户通过 GUI 触发预演
- **WHEN** 预演完成
- **THEN** GUI MUST 展示通过/失败状态与报告入口
- **THEN** GUI MUST 展示失败关键原因与建议动作

### Requirement: 私网交付证据
系统 MUST 在离线交付目录内生成可复核的证据文件，供私网管理员核验。

#### Scenario: 证据文件齐全
- **GIVEN** 用户完成高级下载流程
- **WHEN** 任务结束
- **THEN** 输出目录 MUST 包含依赖树、覆盖报告、可安装性报告与源码处理指引
- **THEN** 报告 MUST 包含执行时间、目标环境参数与关键命令摘要
