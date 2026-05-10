## ADDED Requirements

### Requirement: 锁定清单驱动离线 requirements 生成
当解析阶段产出锁定依赖列表时，系统 MUST 使用该列表生成 `requirements-offline.txt`，而不是通过输出目录扫描推断版本。

#### Scenario: CLI 在锁定模式下生成离线清单
- **WHEN** CLI 解析阶段返回锁定依赖列表并完成下载
- **THEN** 系统 MUST 使用锁定依赖列表写入 `requirements-offline.txt`
- **THEN** `requirements-offline.txt` MUST 不包含锁定列表之外的版本条目

#### Scenario: GUI 在锁定模式下生成离线清单
- **WHEN** GUI Worker 解析阶段返回锁定依赖列表并完成下载
- **THEN** GUI MUST 与 CLI 使用同一清单生成语义
- **THEN** 生成结果 MUST 与锁定依赖列表一致

### Requirement: 无锁定清单时的兼容生成路径
当解析阶段未产出锁定依赖列表时，系统 MUST 继续支持目录扫描生成离线清单，并明确标注为非锁定模式。

#### Scenario: uv 不可用时回退兼容模式
- **WHEN** 系统因 uv 不可用或解析回退而未获得锁定依赖列表
- **THEN** 系统 MUST 使用目录扫描生成 `requirements-offline.txt`
- **THEN** 系统 MUST 在报告或日志中标注 `manifest_mode=non_lock`

#### Scenario: Windows 与 Linux 一致模式标识
- **WHEN** 用户分别在 Windows 与 Linux 执行非锁定模式流程
- **THEN** 两端输出 MUST 均包含一致的模式标识语义
- **THEN** 模式标识 MUST 可被自动化测试读取

### Requirement: 锁定清单与产物一致性对账
下载完成后系统 MUST 生成锁定与实际产物的一致性对账结果，用于识别缺失项与污染项。

#### Scenario: 识别缺失与仅源码项
- **WHEN** 锁定清单中的某些依赖未找到对应 wheel 或仅存在源码包
- **THEN** 对账结果 MUST 输出 `missing_from_artifacts` 与 `source_only` 列表
- **THEN** 日志摘要 MUST 指向对应报告文件

#### Scenario: 识别输出目录中的额外污染项
- **WHEN** 输出目录存在不在锁定清单中的额外产物
- **THEN** 对账结果 MUST 输出 `extra_artifacts_not_in_lock` 列表
- **THEN** 系统 MUST 不将这些额外项写入锁定模式下的 `requirements-offline.txt`
