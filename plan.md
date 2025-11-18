# Auto-Wheel 优化方案

## 1. 问题分析

### 1.1 问题现象

执行 `auto-wheel -p 3.9 -pkg pytest` 后，在 Python 3.9 环境中安装时报错：

```
ERROR: Could not find a version that satisfies the requirement exceptiongroup>=1; python_version < "3.11" (from pytest)
ERROR: No matching distribution found for exceptiongroup>=1; python_version < "3.11"
```

### 1.2 根本原因

**pip download 对环境标记（Environment Markers）的处理缺陷**

当使用 `pip download --python-version 3.9` 进行跨版本下载时，pip 无法正确解析和下载带有环境标记的条件依赖。

#### 技术细节

pytest 8.x 的依赖声明（摘自 `requires_dist`）：

```python
Requires-Dist: exceptiongroup>=1.0.0rc8; python_version < "3.11"
Requires-Dist: tomli>=1; python_version < "3.11"
```

这些依赖只在 Python < 3.11 时需要。但 pip 在当前机器（假设 Python 3.11+）执行下载时：
- 使用当前环境评估 markers，而非目标环境
- 导致条件依赖被跳过

#### 受影响的典型包

| 包名 | 条件依赖 | 影响版本 |
|------|----------|----------|
| pytest | exceptiongroup, tomli | Python < 3.11 |
| typing-extensions | - | Python < 3.8 |
| importlib-metadata | - | Python < 3.8 |
| asyncio | async-timeout | Python < 3.11 |

### 1.3 当前代码分析

**downloader.py** 核心逻辑（第67-111行）：

```python
def _build_pip_command(self, packages: List[str], dry_run: bool = False) -> List[str]:
    cmd = [
        sys.executable, "-m", "pip", "download",
        "--dest", str(self.output_dir),
        "--python-version", self.python_version,
        "--platform", self.platform,
        "--implementation", self.implementation,
        "--abi", self.abi,
        "--only-binary", self.only_binary,
    ]
    cmd.extend(packages)
    return cmd
```

问题：直接依赖 pip 的依赖解析，无法控制 marker 评估环境。

---

## 2. 解决方案

### 2.1 方案概述

采用**两阶段处理**策略：使用 `uv pip compile` 进行准确的依赖解析，然后使用 `pip download` 下载包。

**重要说明**：uv **没有** `pip download` 子命令，但提供了强大的 `pip compile` 功能，可以正确解析环境标记。

**为什么选择 uv pip compile？**

| 特性 | pip freeze/compile | uv pip compile |
|------|-----|-----|
| 速度 | 基准 | 10-100x 更快 |
| 环境标记处理 | ❌ 使用当前环境 | ✅ 使用目标环境 |
| 跨平台解析 | ⚠️ 需要虚拟环境 | ✅ 支持 `--python-version` |
| 依赖解析 | SAT 求解器 | 现代 Rust 实现 |
| 通用锁定 | ❌ 不支持 | ✅ 支持 `--universal` |

### 2.2 架构设计

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐
│   CLI       │────▶│  Resolver    │────▶│  Downloader │────▶│   Output    │
│  (cli.py)   │     │  (新增模块)   │     │ (downloader)│     │   Wheels    │
└─────────────┘     └──────┬───────┘     └─────────────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼                         ▼
       ┌─────────────┐          ┌─────────────┐
       │ UvResolver  │          │ PipResolver │
       │  (推荐)      │          │  (回退)      │
       └─────────────┘          └─────────────┘
```

**两阶段工作流程**：

```
阶段一：依赖解析
┌──────────┐    uv pip compile     ┌──────────────────┐
│ pytest   │ ─────────────────────▶│ resolved.txt     │
└──────────┘  --python-version 3.9 │ - pytest==8.4.2  │
                                   │ - exceptiongroup │
                                   │ - pluggy         │
                                   │ - ...            │
                                   └──────────────────┘

阶段二：包下载
┌──────────────────┐    pip download    ┌──────────────┐
│ resolved.txt     │ ─────────────────▶ │ *.whl files  │
└──────────────────┘  --python-version  └──────────────┘
```

### 2.3 实现策略

#### 策略：自动检测 + 优雅回退（推荐）

```python
class DependencyResolver:
    """依赖解析器"""

    @staticmethod
    def resolve(
        packages: List[str],
        python_version: str,
        platform: Optional[str] = None
    ) -> List[str]:
        """解析依赖并返回完整包列表"""

        # 优先使用 uv
        if shutil.which("uv"):
            return UvResolver.resolve(packages, python_version, platform)

        # 回退到 pip（保持现有行为）
        return packages  # 直接返回，让 pip download 处理
```

**优点**：
- 用户无需额外配置
- 向后兼容现有用户
- 遵循 KISS 原则
- 增量改进，风险最小

---

## 3. 详细实现计划

### 3.1 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `resolver.py` | 新增 | 依赖解析器模块（核心） |
| `downloader.py` | 小改 | 集成解析器，调整下载流程 |
| `config.py` | 小改 | 添加 `use_uv_resolver` 配置项 |
| `pyproject.toml` | 小改 | 添加 uv 可选依赖说明 |

### 3.2 核心代码变更

#### 3.2.1 新增依赖解析器模块（resolver.py）

```python
"""
依赖解析器模块 - 使用 uv pip compile 进行准确的依赖解析
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional


class DependencyResolver:
    """依赖解析器"""

    def __init__(
        self,
        python_version: str,
        platform: Optional[str] = None,
        index_url: Optional[str] = None,
        verbose: bool = False
    ):
        self.python_version = python_version
        self.platform = platform
        self.index_url = index_url
        self.verbose = verbose
        self.use_uv = shutil.which("uv") is not None

    def resolve(self, packages: List[str]) -> List[str]:
        """
        解析依赖并返回完整的包列表（带版本号）

        Args:
            packages: 输入包列表

        Returns:
            解析后的完整依赖列表，格式如 ["pytest==8.4.2", "exceptiongroup==1.2.0", ...]
        """
        if self.use_uv:
            return self._resolve_with_uv(packages)

        # 回退：直接返回原始包列表，让 pip download 处理
        if self.verbose:
            print("uv 未安装，使用 pip 默认解析（可能缺少条件依赖）")
        return packages

    def _resolve_with_uv(self, packages: List[str]) -> List[str]:
        """使用 uv pip compile 解析依赖"""

        if self.verbose:
            print(f"使用 uv pip compile 解析依赖 (Python {self.python_version})")

        # 创建临时 requirements 文件
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.in',
            delete=False,
            encoding='utf-8'
        ) as f:
            for pkg in packages:
                f.write(f"{pkg}\n")
            input_file = f.name

        try:
            # 构建 uv pip compile 命令
            cmd = [
                "uv", "pip", "compile",
                input_file,
                "--python-version", self.python_version,
            ]

            # 添加平台参数（如果指定）
            if self.platform and self.platform.lower() != "auto":
                # uv 使用 --python-platform 而非 --platform
                cmd.extend(["--python-platform", self._convert_platform(self.platform)])

            # 添加索引 URL
            if self.index_url:
                cmd.extend(["--index-url", self.index_url])

            if self.verbose:
                print(f"执行: {' '.join(cmd)}")

            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            # 解析输出
            resolved = self._parse_compile_output(result.stdout)

            if self.verbose:
                print(f"解析完成，共 {len(resolved)} 个包")

            return resolved

        except subprocess.CalledProcessError as e:
            print(f"uv pip compile 失败: {e.stderr}", file=sys.stderr)
            # 回退到原始包列表
            return packages

        finally:
            # 清理临时文件
            Path(input_file).unlink(missing_ok=True)

    def _convert_platform(self, platform: str) -> str:
        """
        将 pip 风格的平台标识转换为 uv 风格

        pip: win_amd64, manylinux2014_x86_64
        uv:  windows, linux, macos (或 target triple)
        """
        platform_lower = platform.lower()

        if "win" in platform_lower:
            return "windows"
        elif "linux" in platform_lower or "manylinux" in platform_lower:
            return "linux"
        elif "macos" in platform_lower or "darwin" in platform_lower:
            return "macos"

        # 默认返回原值
        return platform

    def _parse_compile_output(self, output: str) -> List[str]:
        """解析 uv pip compile 的输出"""
        resolved = []

        for line in output.strip().split('\n'):
            line = line.strip()

            # 跳过注释和空行
            if not line or line.startswith('#'):
                continue

            # 跳过 via 注释行（缩进的行）
            if line.startswith('# via'):
                continue

            # 提取包名和版本（格式: package==version）
            if '==' in line:
                # 处理可能的环境标记
                pkg_spec = line.split(';')[0].strip()
                resolved.append(pkg_spec)

        return resolved
```

#### 3.2.2 修改 WheelDownloader 类（downloader.py）

```python
import shutil
from .resolver import DependencyResolver

class WheelDownloader:
    def __init__(
        self,
        python_version: str,
        output_dir: str = "./downloads",
        platform: Optional[str] = None,
        implementation: str = "cp",
        abi: Optional[str] = None,
        only_binary: str = ":all:",
        verbose: bool = False,
        config_pip_args: Optional[List[str]] = None,
        max_attempts: int = 3,
        retry_delay: float = 3.0,
        command_timeout: Optional[int] = None,
        use_uv_resolver: bool = True  # 新增参数
    ):
        # ... 现有初始化代码 ...

        self.use_uv_resolver = use_uv_resolver

        # 初始化解析器
        if use_uv_resolver:
            self.resolver = DependencyResolver(
                python_version=python_version,
                platform=platform,
                index_url=self._extract_index_url(config_pip_args),
                verbose=verbose
            )
        else:
            self.resolver = None

    def _extract_index_url(self, pip_args: Optional[List[str]]) -> Optional[str]:
        """从 pip 参数中提取 index URL"""
        if not pip_args:
            return None

        for i, arg in enumerate(pip_args):
            if arg == "--index-url" and i + 1 < len(pip_args):
                return pip_args[i + 1]

        return None

    def download_packages(
        self,
        packages: List[str],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """下载指定包（优化版）"""

        # 阶段一：依赖解析
        if self.resolver and self.use_uv_resolver:
            if self.verbose:
                print("阶段一：解析依赖...")

            resolved_packages = self.resolver.resolve(packages)

            if self.verbose:
                print(f"解析结果: {resolved_packages}")
        else:
            resolved_packages = packages

        # 阶段二：下载包（使用现有 pip download 逻辑）
        if self.verbose:
            print("阶段二：下载包...")

        cmd = self._build_pip_command(resolved_packages, dry_run=dry_run)
        return self._execute_download(cmd, dry_run=dry_run)

    # _build_pip_command 和 _execute_download 保持不变
```

#### 3.2.3 配置更新（config.py）

```python
class Config:
    DEFAULT_CONFIG = {
        # ... 现有配置 ...
        "use_uv_resolver": True,  # 是否使用 uv 进行依赖解析
    }

    @property
    def use_uv_resolver(self) -> bool:
        """是否使用 uv 解析器"""
        return self.config_data.get("use_uv_resolver", True)
```

#### 3.2.4 主程序更新（main.py）

```python
def main():
    # ... 现有代码 ...

    # 初始化下载器
    downloader = WheelDownloader(
        python_version=python_version,
        output_dir=output_dir,
        platform=platform if platform != "auto" else None,
        implementation=args.implementation,
        abi=args.abi,
        only_binary=args.only_binary,
        verbose=args.verbose,
        config_pip_args=config.get_pip_args(),
        max_attempts=max(1, config.retries),
        retry_delay=3.0,
        command_timeout=max(config.timeout, 60),
        use_uv_resolver=config.use_uv_resolver  # 新增
    )
```

### 3.3 UV pip compile 命令参考

#### 基本用法

```bash
# 从输入文件解析依赖
echo "pytest" | uv pip compile - --python-version 3.9

# 从 requirements.in 文件解析
uv pip compile requirements.in --python-version 3.9

# 指定目标平台
uv pip compile requirements.in --python-version 3.9 --python-platform windows

# 使用国内镜像
uv pip compile requirements.in --python-version 3.9 --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 生成通用锁定文件（包含所有平台的标记）
uv pip compile requirements.in --universal
```

#### 输出示例

```
# This file was autogenerated by uv via the following command:
#    uv pip compile requirements.in --python-version 3.9
colorama==0.4.6
    # via pytest
exceptiongroup==1.2.0
    # via pytest
iniconfig==2.1.0
    # via pytest
packaging==25.0
    # via pytest
pluggy==1.6.0
    # via pytest
pytest==8.4.2
tomli==2.0.1
    # via pytest
```

#### uv pip compile 与 pip-tools 对比

| 功能 | pip-compile | uv pip compile |
|------|-------------|----------------|
| 速度 | 基准 | 10-100x 更快 |
| Python 版本 | 需要虚拟环境 | `--python-version` |
| 平台 | 需要虚拟环境 | `--python-platform` |
| 环境标记 | 当前环境 | 目标环境 |
| 通用锁定 | ❌ | `--universal` |

---

## 4. 测试计划

### 4.1 单元测试

```python
# tests/test_resolver.py

import shutil
from auto_wheel.resolver import DependencyResolver

def test_resolver_with_uv():
    """测试使用 uv 解析依赖"""
    if not shutil.which("uv"):
        pytest.skip("uv not installed")

    resolver = DependencyResolver(
        python_version="3.9",
        verbose=True
    )

    result = resolver.resolve(["pytest"])

    # 应该包含 pytest 及其所有依赖
    assert any("pytest==" in pkg for pkg in result)
    # 关键：应该包含 exceptiongroup（条件依赖）
    assert any("exceptiongroup==" in pkg for pkg in result)

def test_resolver_fallback():
    """测试 uv 不可用时的回退行为"""
    resolver = DependencyResolver(
        python_version="3.9"
    )
    resolver.use_uv = False  # 模拟 uv 不可用

    result = resolver.resolve(["pytest"])

    # 回退时应直接返回原始包列表
    assert result == ["pytest"]

def test_platform_conversion():
    """测试平台标识转换"""
    resolver = DependencyResolver(python_version="3.9")

    assert resolver._convert_platform("win_amd64") == "windows"
    assert resolver._convert_platform("manylinux2014_x86_64") == "linux"
    assert resolver._convert_platform("macosx_10_9_x86_64") == "macos"

def test_parse_compile_output():
    """测试解析 uv pip compile 输出"""
    resolver = DependencyResolver(python_version="3.9")

    output = """# This file was autogenerated by uv
colorama==0.4.6
    # via pytest
exceptiongroup==1.2.0
    # via pytest
pytest==8.4.2
"""

    result = resolver._parse_compile_output(output)

    assert "colorama==0.4.6" in result
    assert "exceptiongroup==1.2.0" in result
    assert "pytest==8.4.2" in result
    assert len(result) == 3
```

### 4.2 集成测试

```bash
# 测试用例 1: pytest 及其条件依赖（核心测试）
auto-wheel -p 3.9 -pkg pytest -v

# 验证下载的包
# 预期结果：应包含 exceptiongroup, tomli 等条件依赖
Get-ChildItem downloads/*.whl | Select-Object Name

# 测试用例 2: 离线安装验证（在 Python 3.9 环境中）
cd downloads
pip install --no-index --find-links=. -r requirements-offline.txt
python -c "import pytest; print(pytest.__version__)"

# 测试用例 3: 验证 exceptiongroup 已正确安装
python -c "import exceptiongroup; print(exceptiongroup.__version__)"
```

### 4.3 边界测试

| 测试场景 | 预期行为 |
|----------|----------|
| uv 未安装 | 警告并回退到 pip 默认行为 |
| uv pip compile 失败 | 回退到原始包列表 |
| 无效 Python 版本 | uv 报错，回退处理 |
| 网络超时 | 重试机制生效 |
| 空包列表 | 友好错误提示 |

---

## 5. 用户文档更新

### 5.1 README 更新

```markdown
## 推荐：安装 uv 获得更好的依赖解析

auto-wheel 支持使用 [uv](https://github.com/astral-sh/uv) 进行依赖解析，
能够更准确地处理带有环境标记的条件依赖（如 `exceptiongroup>=1; python_version < "3.11"`）。

### 安装 uv

```powershell
# Windows (PowerShell) - 推荐
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip
pip install uv
```

### 验证安装

```powershell
uv --version
```

### 工作原理

当 uv 可用时，auto-wheel 会：
1. 使用 `uv pip compile` 解析完整依赖树（正确处理环境标记）
2. 使用 `pip download` 下载所有解析出的包

如果 uv 不可用，将回退到原有行为（直接使用 pip download）。
```

### 5.2 配置文件示例

```json
{
    "index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "trusted_hosts": ["pypi.tuna.tsinghua.edu.cn"],
    "default_python_version": "3.9",
    "download_dir": "./downloads",
    "use_uv_resolver": true,
    "timeout": 300,
    "retries": 3
}
```

### 5.3 常见问题

**Q: 为什么需要安装 uv？**

A: pip download 在跨版本下载时，会使用当前环境评估环境标记，导致某些条件依赖被跳过。
uv pip compile 可以正确地为目标 Python 版本解析依赖。

**Q: 不安装 uv 可以使用吗？**

A: 可以，auto-wheel 会自动回退到原有行为。但对于有复杂条件依赖的包（如 pytest），
可能会缺少部分依赖。

---

## 6. 迁移指南

### 6.1 对现有用户的影响

**无破坏性变更**：
- 所有现有 CLI 参数保持不变
- 配置文件完全向后兼容
- 默认行为与当前一致（如果没有 uv）

### 6.2 升级步骤

1. 更新 auto-wheel 到新版本
2. （可选）安装 uv 获得更好的依赖解析
3. 无需修改任何配置或命令

---

## 7. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| uv API 变更 | 中 | 锁定 uv 最低版本，监控更新 |
| uv 安装困难 | 低 | 提供详细安装文档，回退到 pip |
| 网络问题 | 低 | 保留重试机制 |
| 平台兼容性 | 低 | 仅支持 Windows，测试充分 |

---

## 8. 实施时间表

| 阶段 | 任务 | 预计耗时 |
|------|------|----------|
| 1 | 后端抽象层实现 | 1-2 小时 |
| 2 | UvBackend 实现 | 1 小时 |
| 3 | 配置集成 | 30 分钟 |
| 4 | 单元测试 | 1 小时 |
| 5 | 集成测试 | 1 小时 |
| 6 | 文档更新 | 30 分钟 |

**总计：约 5-6 小时**

---

## 9. 后续优化（可选）

### 9.1 短期优化

- [ ] 添加下载进度显示
- [ ] 支持并行下载多个包
- [ ] 缓存已下载的包

### 9.2 长期规划

- [ ] 支持 Linux/macOS 平台
- [ ] 添加依赖冲突检测
- [ ] 支持 lock 文件生成
- [ ] GUI 界面集成 uv 选项

---

## 10. 总结

本方案通过引入 `uv pip compile` 作为依赖解析器，解决了 pip 在跨版本下载时对环境标记处理不完善的问题。

**核心优势**：
1. ✅ 正确解析条件依赖（如 exceptiongroup、tomli）
2. ✅ 依赖解析速度提升 10-100 倍
3. ✅ 保持完全向后兼容（CLI 接口不变）
4. ✅ 遵循 KISS 原则，采用两阶段处理策略

**技术方案**：
```
阶段一：uv pip compile → 解析完整依赖树
阶段二：pip download → 下载所有包
```

**实施建议**：
- 新增 `resolver.py` 模块封装 uv pip compile 逻辑
- 自动检测 uv，不可用时优雅回退
- 在 README 中推荐用户安装 uv
- 通过集成测试验证 pytest 等常见包的依赖完整性
