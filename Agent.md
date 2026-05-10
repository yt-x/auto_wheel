Always respond in Chinese-simplified

# 全局配置

## 语言和环境

- **语言**: 始终使用简体中文回复（包括代码注释和 commit 信息）
- **操作系统**: Windows 11
- **Shell**: PowerShell（`pwsh`/`powershell`）
- **包管理器**: 前端项目使用 pnpm

## 执行规范

- 开始任务前，先扫描可用的技能，匹配则读取 `SKILL.md` 并遵循其执行规范
- 所有沟通、代码注释、文档使用中文，新文件 UTF-8（无 BOM）
- 与本指南冲突的用户显式指令优先，须在前置说明中记录偏差原因

## 响应格式要求

每次回复必须在末尾添加 **执行摘要**，结构化展示本次调用情况：

```markdown
---
## 执行摘要

**Skills 调用**：
- [skill-name]: 用途说明

**MCP 工具调用**：
- [server-name]:[tool-name]: 用途说明

**其他功能**：
- [功能名称]: 用途说明
```

**示例**：

```markdown
---
## 执行摘要

**Skills 调用**：
- code-assistant: 编程任务编排
- get-api-docs: 查询 OpenAI API 文档

**MCP 工具调用**：
- serena:find_symbol: 定位 UserController 类
- serena:replace_symbol_body: 修改 login 方法实现
- context7:query-docs: 查询 React 19 文档

**其他功能**：
- TaskCreate: 创建 3 个子任务跟踪进度
```

**规则**：
- 仅列出实际调用的项，未使用的分类不显示
- 用途说明简短（5-10 字），说明调用目的
- 按调用顺序排列

## Git 操作

**只允许读取，禁止修改**

- 允许：`git log`、`git status`、`git diff`、`git branch`、`git show`
- 禁止：`git commit`、`git push`、`git pull`、`git merge`、`git rebase`、`git reset`

## Windows 注意事项

- 不要在 PowerShell 中调用 Unix 文本工具（`sed`/`awk`/`cut`/`head`/`tail`），使用 PowerShell 原生命令：
  - `head` → `Select-Object -First N`
  - `tail` → `Get-Content -Tail N`
  - 替换 → `-replace` 配合 `Get-Content`/`Set-Content`