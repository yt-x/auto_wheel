## ADDED Requirements

### Requirement: 目标环境依赖覆盖报告
系统 MUST 基于目标 Python 版本、平台、实现与 ABI 生成依赖覆盖报告，并对每个依赖标记覆盖状态。

#### Scenario: 成功生成覆盖报告
- **GIVEN** 用户提供合法的依赖输入与目标环境参数
- **WHEN** 系统完成依赖解析与下载评估
- **THEN** 系统 MUST 输出包含每个依赖状态的覆盖报告文件
- **THEN** 每个依赖 MUST 被标记为 `wheel-ready`、`source-required` 或 `unresolved` 之一

#### Scenario: Windows 与 Linux 覆盖差异可见
- **GIVEN** 相同依赖在 Windows 与 Linux 目标平台上可用发行版不同
- **WHEN** 用户分别执行两个目标平台任务
- **THEN** 两份覆盖报告 MUST 展示差异化状态
- **THEN** 报告 MUST 记录平台与 ABI 维度的上下文信息

### Requirement: 解析失败分类输出
系统 MUST 对解析失败进行分类，并在报告中区分“工具异常”与“依赖不可满足”。

#### Scenario: uv 执行异常触发 pip 解析回退
- **GIVEN** uv 解析阶段发生工具执行错误或环境错误
- **WHEN** 系统判断失败类型为可回退类别
- **THEN** 系统 MUST 回退到 pip 解析路径
- **THEN** 覆盖报告 MUST 记录回退原因与触发阶段

#### Scenario: 依赖天然不可满足不触发无效重试
- **GIVEN** 目标环境不存在匹配版本或 ABI 的发行版
- **WHEN** 解析器识别为不可满足类别
- **THEN** 系统 MUST 直接将相关依赖标记为 `unresolved`
- **THEN** 系统 MUST 给出可读的失败原因摘要
