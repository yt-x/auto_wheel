# Auto-Wheel 优化方案（最终版）

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
       │ UvResolver  │          │   Fallback  │
       │  (推荐)      │          │  (原始列表)  │
       └─────────────┘          └─────────────┘
```

**两阶段工作流程**：

```
阶段一：依赖解析
┌──────────┐    uv pip compile     ┌──────────────────┐
│ pytest   │ ─────────────────────▶│ resolved.txt     │
└──────────┘  --python-version 3.9 │ pytest==8.4.2    │
                                   │ exceptiongroup.. │
                                   │ pluggy==...      │
                                   │ ...              │
                                   └──────────────────┘

阶段二：包下载
┌──────────────────┐    pip download    ┌──────────────┐
│ resolved.txt     │ ─────────────────▶ │ *.whl files  │
└──────────────────┘  --python-version  └──────────────┘
```

### 2.3 实现策略

采用**自动检测 + 优雅回退**策略：

```python
class DependencyResolver:
    """依赖解析器"""

    def resolve(self, packages: List[str]) -> List[str]:
        """解析依赖并返回完整包列表"""

        # 优先使用 uv
        if self.use_uv and shutil.which("uv"):
            return self._resolve_with_uv(packages)

        # 回退到原始列表，让 pip download 处理
        if self.verbose:
            print("未启用 uv 或 uv 不可用，条件依赖可能缺失（例：pytest 需要 exceptiongroup）")
        return packages
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
| `src/auto_wheel/resolver.py` | 新增 | 依赖解析器模块（核心） |
| `src/auto_wheel/downloader.py` | 小改 | 新增 `download_resolved_requirements` 方法 |
| `src/auto_wheel/main.py` | 中改 | 集成解析器，调整主流程 |
| `src/auto_wheel/config.py` | 小改 | 添加 `use_uv_resolver` 配置项 |
| `pyproject.toml` | 小改 | 添加 uv 可选依赖说明 |

### 3.2 核心代码变更

#### 3.2.1 新增依赖解析器模块（src/auto_wheel/resolver.py）

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
        pip_args: Optional[List[str]] = None,
        use_uv: bool = True,
        timeout: Optional[int] = None,
        verbose: bool = False
    ):
        """
        初始化解析器

        Args:
            python_version: 目标 Python 版本（如 "3.9"）
            platform: 目标平台（如 "win_amd64"）
            pip_args: pip 参数列表（用于提取 index-url 等）
            use_uv: 是否启用 uv 解析
            timeout: uv 命令超时时间（秒）
            verbose: 是否输出详细信息
        """
        self.python_version = python_version
        self.platform = platform
        self.pip_args = pip_args or []
        self.use_uv = use_uv
        self.timeout = timeout
        self.verbose = verbose

    def resolve(self, packages: List[str]) -> List[str]:
        """
        解析依赖并返回完整的包列表（带版本号）

        Args:
            packages: 输入包列表（可以带版本约束，如 ["flask>=2.0", "pytest"]）

        Returns:
            解析后的完整依赖列表，格式如 ["pytest==8.4.2", "exceptiongroup==1.2.0", ...]
        """
        if not packages:
            return []

        # 检查是否启用 uv 且可用
        if not self.use_uv:
            if self.verbose:
                print("未启用 uv 解析器，使用原始包列表（条件依赖可能缺失）")
            return packages

        if not shutil.which("uv"):
            if self.verbose:
                print("uv 未安装，使用原始包列表（条件依赖可能缺失）")
            return packages

        # 使用 uv 解析
        return self._resolve_with_uv(packages)

    def _resolve_with_uv(self, packages: List[str]) -> List[str]:
        """使用 uv pip compile 解析依赖"""

        if self.verbose:
            print(f"使用 uv pip compile 解析依赖 (Python {self.python_version})")

        # 创建临时输入文件
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.in',
            delete=False,
            encoding='utf-8'
        ) as f:
            for pkg in packages:
                f.write(f"{pkg}\n")
            input_file = f.name

        # 创建临时输出文件
        output_fd, output_file = tempfile.mkstemp(suffix='.txt', text=True)

        try:
            # 构建 uv pip compile 命令（最小化参数）
            cmd = [
                "uv", "pip", "compile",
                input_file,
                "-o", output_file,
                "--python-version", self.python_version,
            ]

            # 添加平台参数（如果指定）
            if self.platform and self.platform.lower() != "auto":
                platform = self._convert_platform(self.platform)
                cmd.extend(["--python-platform", platform])

            # 转换并添加 pip 参数（index-url 等）
            uv_args = self._convert_pip_args_for_uv(self.pip_args)
            cmd.extend(uv_args)

            if self.verbose:
                print(f"执行: {' '.join(cmd)}")

            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout
            )

            # 读取并解析输出文件
            with open(output_file, 'r', encoding='utf-8') as f:
                resolved = self._parse_requirements_file(f.read())

            if self.verbose:
                print(f"解析完成，共 {len(resolved)} 个包")

            return resolved

        except subprocess.CalledProcessError as e:
            print(f"uv pip compile 失败: {e.stderr}", file=sys.stderr)
            print("回退到原始包列表", file=sys.stderr)
            return packages

        except subprocess.TimeoutExpired:
            print(f"uv pip compile 超时（>{self.timeout}s），回退到原始包列表", file=sys.stderr)
            return packages

        except Exception as e:
            print(f"uv 解析异常: {e}，回退到原始包列表", file=sys.stderr)
            return packages

        finally:
            # 清理临时文件
            Path(input_file).unlink(missing_ok=True)
            try:
                import os
                os.close(output_fd)
            except:
                pass
            Path(output_file).unlink(missing_ok=True)

    def _convert_platform(self, platform: str) -> str:
        """
        将 pip 风格的平台标识转换为 uv 风格

        pip: win_amd64, manylinux2014_x86_64, macosx_10_9_x86_64
        uv:  windows, linux, macos
        """
        platform_lower = platform.lower()

        if "win" in platform_lower:
            return "windows"
        elif "linux" in platform_lower or "manylinux" in platform_lower:
            return "linux"
        elif "macos" in platform_lower or "darwin" in platform_lower:
            return "macos"

        # 默认返回原值（可能是 target triple）
        return platform

    def _convert_pip_args_for_uv(self, pip_args: List[str]) -> List[str]:
        """
        将 pip 参数转换为 uv 兼容的参数

        uv 支持：--index-url, --extra-index-url
        uv 不支持：--trusted-host, --timeout, --retries 等

        Args:
            pip_args: pip 参数列表

        Returns:
            uv 兼容的参数列表
        """
        uv_args = []
        i = 0

        while i < len(pip_args):
            arg = pip_args[i]

            if arg == "--index-url" and i + 1 < len(pip_args):
                uv_args.extend(["--index-url", pip_args[i + 1]])
                i += 2
            elif arg == "--extra-index-url" and i + 1 < len(pip_args):
                uv_args.extend(["--extra-index-url", pip_args[i + 1]])
                i += 2
            elif arg in ["--trusted-host", "--timeout", "--retries"]:
                # 跳过 uv 不支持的参数
                i += 2
            else:
                i += 1

        return uv_args

    def _parse_requirements_file(self, content: str) -> List[str]:
        """
        解析 uv pip compile 生成的 requirements 文件

        Args:
            content: requirements 文件内容

        Returns:
            包列表（格式：package==version）
        """
        resolved = []

        for line in content.strip().split('\n'):
            line = line.strip()

            # 跳过注释和空行
            if not line or line.startswith('#'):
                continue

            # 提取包规范（格式: package==version 或 package==version ; marker）
            if '==' in line:
                # 移除环境标记（如果有）
                pkg_spec = line.split(';')[0].strip()
                # 移除行内注释
                pkg_spec = pkg_spec.split('#')[0].strip()
                if pkg_spec:
                    resolved.append(pkg_spec)

        return resolved
```

#### 3.2.2 修改 WheelDownloader 类（src/auto_wheel/downloader.py）

```python
import tempfile
from pathlib import Path

class WheelDownloader:
    # ... 现有代码保持不变 ...

    def download_resolved_requirements(
        self,
        resolved: List[str],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        下载已解析的依赖列表

        Args:
            resolved: 已解析的包列表（格式：["package==version", ...]）
            dry_run: 是否仅模拟运行

        Returns:
            下载结果字典
        """
        if not resolved:
            return {
                "success": False,
                "error": "空的依赖列表"
            }

        # 写入临时 requirements 文件
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False,
            encoding='utf-8'
        ) as f:
            for pkg in resolved:
                f.write(f"{pkg}\n")
            resolved_file = f.name

        try:
            # 复用现有的 download_from_requirements 方法
            # 这样可以完全复用重试、超时等逻辑（DRY 原则）
            return self.download_from_requirements(resolved_file, dry_run=dry_run)
        finally:
            # 清理临时文件
            Path(resolved_file).unlink(missing_ok=True)
```

#### 3.2.3 主流程对接（src/auto_wheel/main.py）

```python
"""
Main entry point for auto-wheel
"""

import sys
from pathlib import Path

from .cli import parse_arguments, validate_arguments
from .config import Config
from .downloader import WheelDownloader
from .resolver import DependencyResolver
from .requirements_generator import RequirementsGenerator


def read_requirements_file(file_path: str) -> List[str]:
    """
    读取 requirements 文件并提取包列表

    Args:
        file_path: requirements 文件路径

    Returns:
        包列表（过滤空行和注释）
    """
    packages = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()

            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue

            # 跳过 pip 选项（如 -i, --index-url 等）
            if line.startswith('-'):
                continue

            packages.append(line)

    return packages


def main():
    """主入口"""
    try:
        # 解析命令行参数
        args = parse_arguments()

        # 验证参数
        validate_arguments(args)

        # 加载配置
        config = Config(config_path=args.config)

        # 获取 Python 版本
        python_version = args.python_version or config.get("default_python_version")
        if not python_version:
            print("错误: 未指定 Python 版本。使用 -p/--python-version 或在配置中设置 default_python_version", file=sys.stderr)
            sys.exit(1)

        # 获取输出目录
        output_dir = args.output or config.download_dir

        # 获取平台
        platform = args.platform or config.get("default_platform", "auto")

        # 打印配置信息
        print("=" * 60)
        print("Auto Wheel - 离线包下载工具")
        print("=" * 60)
        print(f"Python 版本: {python_version}")
        print(f"平台: {platform}")
        print(f"输出目录: {output_dir}")
        print(f"实现: {args.implementation}")
        print(f"ABI: {args.abi or 'auto'}")

        if args.requirements:
            print(f"Requirements 文件: {args.requirements}")
        elif args.packages:
            print(f"包列表: {', '.join(args.packages)}")

        if config.index_url:
            print(f"索引 URL: {config.index_url}")
        else:
            print("索引 URL: https://pypi.org/simple (默认)")

        # 显示 uv 解析器状态
        use_uv = config.use_uv_resolver
        if use_uv:
            import shutil
            if shutil.which("uv"):
                print("依赖解析: uv pip compile (准确解析条件依赖)")
            else:
                print("依赖解析: pip (uv 未安装，条件依赖可能缺失)")
        else:
            print("依赖解析: pip (未启用 uv)")

        if args.dry_run:
            print("\n[模拟运行模式 - 不会实际下载文件]")

        print("=" * 60)
        print()

        # 准备包列表
        if args.requirements:
            # 从 requirements 文件读取包列表
            print(f"读取 requirements 文件: {args.requirements}")
            packages = read_requirements_file(args.requirements)
            print(f"发现 {len(packages)} 个包")
        else:
            # 使用命令行指定的包列表
            packages = args.packages

        # 阶段一：依赖解析
        print("\n阶段一：解析依赖...")
        resolver = DependencyResolver(
            python_version=python_version,
            platform=platform if platform != "auto" else None,
            pip_args=config.get_pip_args(),
            use_uv=use_uv,
            timeout=config.timeout,
            verbose=args.verbose
        )

        resolved_packages = resolver.resolve(packages)

        if args.verbose:
            print(f"\n解析后的包列表:")
            for pkg in resolved_packages:
                print(f"  - {pkg}")

        # 阶段二：下载包
        print(f"\n阶段二：下载包...")

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
            command_timeout=max(config.timeout, 60)
        )

        # 下载已解析的包
        result = downloader.download_resolved_requirements(
            resolved_packages,
            dry_run=args.dry_run
        )

        # 检查结果
        if not result["success"]:
            print("\n下载失败!", file=sys.stderr)
            print(result.get("error", "未知错误"), file=sys.stderr)
            sys.exit(1)

        if args.dry_run:
            print("\n模拟运行完成。")
            print(f"将执行的命令:\n{result.get('command', 'N/A')}")
            return

        print("\n下载完成!")
        print(f"包保存至: {output_dir}")

        # 生成 requirements 文件
        print("\n生成离线 requirements 文件...")
        generator = RequirementsGenerator(
            output_dir=output_dir,
            with_hashes=args.with_hashes
        )

        try:
            req_file = generator.generate()
            print(f"Requirements 文件: {req_file}")

            # 生成安装脚本
            script_file = generator.generate_install_script()
            print(f"安装脚本: {script_file}")
            print(f"  同时生成: {Path(output_dir) / 'install.bat'}")

            print("\n" + "=" * 60)
            print("设置完成！离线安装步骤:")
            print("=" * 60)
            print(f"1. 将 '{Path(output_dir).name}' 文件夹复制到离线机器")
            print(f"2. 运行安装命令:")
            print(f"   pip install --no-index --find-links={Path(output_dir).name} -r {Path(output_dir).name}/requirements-offline.txt")
            print("   或执行安装脚本:")
            print(f"   - Windows: cd {Path(output_dir).name} && install.bat")
            print("=" * 60)

        except Exception as e:
            print(f"\n警告: 生成 requirements 文件失败: {e}", file=sys.stderr)
            print("您仍可手动安装包:")
            print(f"  pip install --no-index --find-links={output_dir} <package_name>")

    except KeyboardInterrupt:
        print("\n\n操作被用户取消。", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        if args.verbose if 'args' in locals() else False:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

#### 3.2.4 配置更新（src/auto_wheel/config.py）

```python
class Config:
    DEFAULT_CONFIG = {
        "index_url": "",
        "trusted_hosts": [],
        "extra_index_urls": [],
        "default_python_version": "3.9",
        "default_platform": "auto",
        "download_dir": "./downloads",
        "timeout": 300,
        "retries": 3,
        "use_uv_resolver": False  # 新增：默认 False（保守策略）
    }

    # ... 现有代码 ...

    @property
    def use_uv_resolver(self) -> bool:
        """是否使用 uv 解析器"""
        return self.config_data.get("use_uv_resolver", False)
```

### 3.3 UV pip compile 命令参考

#### 基本用法

```bash
# 从输入文件解析依赖
echo "pytest" | uv pip compile - --python-version 3.9

# 从 requirements.in 文件解析
uv pip compile requirements.in -o requirements.txt --python-version 3.9

# 指定目标平台
uv pip compile requirements.in -o requirements.txt --python-version 3.9 --python-platform windows

# 使用国内镜像
uv pip compile requirements.in -o requirements.txt --python-version 3.9 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
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

#### 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--python-version` | 目标 Python 版本 | `--python-version 3.9` |
| `--python-platform` | 目标平台 | `--python-platform windows` |
| `--index-url` | PyPI 索引 URL | `--index-url https://pypi.org/simple` |
| `--extra-index-url` | 额外索引 URL | `--extra-index-url https://...` |
| `-o` | 输出文件 | `-o requirements.txt` |

**重要**：根据 uv 官方文档，在明确指定 `--python-version` 和 `--python-platform` 时，uv 会按目标环境评估 environment markers，输出文件会自动保留必要标记，**无需额外的 `--no-strip-markers` 参数**。

---

## 4. 测试计划

### 4.1 单元测试

```python
# tests/test_resolver.py

import shutil
import pytest
from auto_wheel.resolver import DependencyResolver

def test_resolver_with_uv():
    """测试使用 uv 解析依赖"""
    if not shutil.which("uv"):
        pytest.skip("uv 未安装")

    resolver = DependencyResolver(
        python_version="3.9",
        use_uv=True,
        verbose=True
    )

    result = resolver.resolve(["pytest"])

    # 应该包含 pytest 及其所有依赖
    assert any("pytest==" in pkg for pkg in result)
    # 关键：应该包含 exceptiongroup（条件依赖）
    assert any("exceptiongroup==" in pkg for pkg in result)
    # 应该包含 tomli（条件依赖）
    assert any("tomli==" in pkg for pkg in result)

def test_resolver_fallback():
    """测试 uv 不可用时的回退行为"""
    resolver = DependencyResolver(
        python_version="3.9",
        use_uv=False
    )

    result = resolver.resolve(["pytest"])

    # 回退时应直接返回原始包列表
    assert result == ["pytest"]

def test_platform_conversion():
    """测试平台标识转换"""
    resolver = DependencyResolver(python_version="3.9")

    assert resolver._convert_platform("win_amd64") == "windows"
    assert resolver._convert_platform("manylinux2014_x86_64") == "linux"
    assert resolver._convert_platform("macosx_10_9_x86_64") == "macos"

def test_pip_args_conversion():
    """测试 pip 参数转换"""
    resolver = DependencyResolver(python_version="3.9")

    pip_args = [
        "--index-url", "https://pypi.org/simple",
        "--trusted-host", "pypi.org",
        "--extra-index-url", "https://test.pypi.org/simple",
        "--timeout", "300"
    ]

    uv_args = resolver._convert_pip_args_for_uv(pip_args)

    # 应该保留 index-url 和 extra-index-url
    assert "--index-url" in uv_args
    assert "https://pypi.org/simple" in uv_args
    assert "--extra-index-url" in uv_args
    assert "https://test.pypi.org/simple" in uv_args

    # 应该过滤掉 trusted-host 和 timeout
    assert "--trusted-host" not in uv_args
    assert "--timeout" not in uv_args

def test_parse_requirements_file():
    """测试解析 requirements 文件输出"""
    resolver = DependencyResolver(python_version="3.9")

    content = """# This file was autogenerated by uv
colorama==0.4.6
    # via pytest
exceptiongroup==1.2.0
    # via pytest
pytest==8.4.2
"""

    result = resolver._parse_requirements_file(content)

    assert "colorama==0.4.6" in result
    assert "exceptiongroup==1.2.0" in result
    assert "pytest==8.4.2" in result
    assert len(result) == 3

def test_read_requirements_file():
    """测试读取 requirements 文件"""
    from auto_wheel.main import read_requirements_file
    import tempfile

    content = """# 测试 requirements 文件
pytest>=7.0
flask

# 空行测试

requests==2.28.0
-i https://pypi.org/simple  # 应该被跳过
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(content)
        temp_file = f.name

    try:
        result = read_requirements_file(temp_file)

        assert "pytest>=7.0" in result
        assert "flask" in result
        assert "requests==2.28.0" in result
        assert len(result) == 3  # 不应包含注释和 pip 选项

    finally:
        Path(temp_file).unlink(missing_ok=True)
```

### 4.2 集成测试

```powershell
# 测试用例 1: pytest 及其条件依赖（核心测试）
# 启用 uv 解析器
auto-wheel -p 3.9 -pkg pytest -v -c config_with_uv.json

# 验证下载的包
Get-ChildItem downloads/*.whl | Select-Object Name

# 预期结果：应包含以下文件
# - pytest-8.4.2-py3-none-any.whl
# - exceptiongroup-1.2.0-py3-none-any.whl
# - tomli-2.0.1-py3-none-any.whl
# - pluggy-1.6.0-py3-none-any.whl
# - iniconfig-2.1.0-py3-none-any.whl
# - packaging-25.0-py3-none-any.whl
# - colorama-0.4.6-py2.py3-none-any.whl (Windows)

# 测试用例 2: 离线安装验证（在 Python 3.9 环境中）
cd downloads
pip install --no-index --find-links=. -r requirements-offline.txt

# 验证安装成功
python -c "import pytest; print(f'pytest: {pytest.__version__}')"
python -c "import exceptiongroup; print(f'exceptiongroup: {exceptiongroup.__version__}')"

# 测试用例 3: requirements.txt 输入
# 创建测试 requirements 文件
echo "pytest>=8.0`nflask>=2.0" > test-requirements.txt

auto-wheel -p 3.9 -r test-requirements.txt -c config_with_uv.json

# 验证包含 pytest 和 flask 的所有依赖

# 测试用例 4: 未启用 uv 的行为（回退测试）
auto-wheel -p 3.9 -pkg pytest -v

# 预期：提示未启用 uv，可能缺少条件依赖
```

### 4.3 边界测试

| 测试场景 | 预期行为 | 验证方法 |
|----------|----------|----------|
| uv 未安装 | 警告并回退到原始包列表 | 检查输出提示 |
| uv pip compile 失败 | 捕获错误并回退 | 模拟网络故障 |
| 无效 Python 版本 | uv 报错，友好提示 | `auto-wheel -p 2.7 -pkg pytest` |
| 空包列表 | 返回空列表，不执行下载 | `resolve([])` |
| 超时 | 捕获超时异常并回退 | 设置极短 timeout |
| requirements 文件不存在 | validate_arguments 报错 | 测试文件路径验证 |

---

## 5. 用户文档更新

### 5.1 README 更新

```markdown
## 推荐：安装 uv 获得更好的依赖解析

auto-wheel 支持使用 [uv](https://github.com/astral-sh/uv) 进行依赖解析，
能够更准确地处理带有环境标记的条件依赖（如 `exceptiongroup>=1; python_version < "3.11"`）。

### 为什么需要 uv？

pip download 在跨版本下载时，会使用当前环境评估环境标记，导致某些条件依赖被跳过。
例如：
- 在 Python 3.11+ 环境中为 Python 3.9 下载 pytest
- pytest 的条件依赖 `exceptiongroup` 和 `tomli` 不会被下载
- 在 Python 3.9 环境中安装时报错

uv pip compile 可以正确地为目标 Python 版本解析依赖。

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

### 启用 uv 解析器

在 `config.json` 中添加：

```json
{
    "use_uv_resolver": true
}
```

或创建配置文件：

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

然后执行：

```powershell
auto-wheel -p 3.9 -pkg pytest -c config.json
```

### 工作原理

当 uv 可用且启用时，auto-wheel 会：
1. **阶段一**：使用 `uv pip compile` 解析完整依赖树（正确处理环境标记）
2. **阶段二**：使用 `pip download` 下载所有解析出的包

如果 uv 不可用，将回退到原有行为（直接使用 pip download），但会提示可能缺少条件依赖。
```

### 5.2 配置文件示例

**config.json** (推荐配置)

```json
{
    "index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "trusted_hosts": ["pypi.tuna.tsinghua.edu.cn"],
    "default_python_version": "3.9",
    "default_platform": "auto",
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
可能会缺少部分依赖（如 exceptiongroup、tomli）。

**Q: use_uv_resolver 为什么默认是 False？**

A: 采用保守策略，确保向后兼容。用户可以在配置文件中显式启用。

**Q: 如何验证 uv 解析器是否生效？**

A: 运行时会显示 "依赖解析: uv pip compile (准确解析条件依赖)" 或
"依赖解析: pip (uv 未安装，条件依赖可能缺失)"。

**Q: 如果 uv pip compile 失败会怎样？**

A: 自动回退到原始包列表，并打印错误信息。确保下载流程不会中断。

---

## 6. 迁移指南

### 6.1 对现有用户的影响

**无破坏性变更**：
- 所有现有 CLI 参数保持不变
- 配置文件完全向后兼容
- 默认行为与当前一致（use_uv_resolver: false）

### 6.2 升级步骤

1. **更新 auto-wheel 到新版本**
   ```powershell
   pip install --upgrade auto-wheel
   ```

2. **（可选）安装 uv 获得更好的依赖解析**
   ```powershell
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. **（可选）启用 uv 解析器**
   在 `config.json` 中添加：
   ```json
   {
       "use_uv_resolver": true
   }
   ```

4. **验证**
   ```powershell
   auto-wheel -p 3.9 -pkg pytest -c config.json -v
   ```

---

## 7. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| uv API 变更 | 中 | 锁定 uv 最低版本要求，监控更新 |
| uv 安装困难 | 低 | 提供详细安装文档，自动回退到 pip |
| 解析超时 | 低 | 可配置 timeout，自动回退 |
| 平台兼容性 | 低 | 仅支持 Windows，测试充分 |
| requirements 文件格式 | 低 | 测试覆盖常见格式 |

---

## 8. 实施时间表

| 阶段 | 任务 | 预计耗时 |
|------|------|----------|
| 1 | 实现 resolver.py | 2 小时 |
| 2 | 修改 downloader.py | 30 分钟 |
| 3 | 修改 main.py | 1.5 小时 |
| 4 | 修改 config.py | 15 分钟 |
| 5 | 单元测试 | 1.5 小时 |
| 6 | 集成测试 | 1 小时 |
| 7 | 文档更新 | 30 分钟 |

**总计：约 7 小时**

---

## 9. 后续优化（可选）

### 9.1 短期优化

- [ ] 添加 `--use-uv` CLI 参数，覆盖配置文件
- [ ] 下载进度显示优化
- [ ] 支持并行下载多个包
- [ ] 缓存已下载的包

### 9.2 长期规划

- [ ] 支持 Linux/macOS 平台
- [ ] 添加依赖冲突检测
- [ ] 支持 lock 文件生成（兼容 uv.lock 格式）
- [ ] GUI 界面集成 uv 选项

---

## 10. 总结

本方案通过引入 `uv pip compile` 作为依赖解析器，解决了 pip 在跨版本下载时对环境标记处理不完善的问题。

### 核心优势

1. ✅ **正确解析条件依赖**：如 exceptiongroup、tomli 等
2. ✅ **依赖解析速度提升 10-100 倍**：得益于 uv 的 Rust 实现
3. ✅ **保持完全向后兼容**：CLI 接口不变，默认行为不变
4. ✅ **遵循 KISS 原则**：采用两阶段处理策略，最小化变更

### 技术方案

```
阶段一：uv pip compile → 解析完整依赖树
阶段二：pip download → 下载所有包
```

### 关键设计决策

1. **保守的默认值**：`use_uv_resolver: false`，确保向后兼容
2. **优雅回退**：uv 不可用时自动回退，不中断流程
3. **DRY 原则**：复用现有的 `download_from_requirements` 方法
4. **参数转换**：`_convert_pip_args_for_uv` 确保 pip 参数正确传递给 uv
5. **统一处理**：`-r` 和 `-pkg` 输入都通过解析器处理，行为一致

### 实施建议

- 新增 `resolver.py` 模块封装 uv pip compile 逻辑
- 自动检测 uv，不可用时优雅回退
- 在 README 中推荐用户安装 uv
- 通过集成测试验证 pytest 等常见包的依赖完整性
- 提供清晰的用户提示（启用/未启用 uv 的差异）

---

## 附录：参考资料

- [uv 官方文档](https://docs.astral.sh/uv/)
- [uv pip compile 文档](https://docs.astral.sh/uv/pip/compile/)
- [PEP 508 - Dependency specification](https://peps.python.org/pep-0508/)
- [Environment Markers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/#environment-markers)
