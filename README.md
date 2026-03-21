# Auto Wheel

自动下载 Python wheel 包至本地，用于离线环境安装。

## 功能特性

- 自动下载指定 Python 版本的 wheel 包及其所有依赖
- 默认优先下载 wheel；仅在识别到“无可用 wheel/发行版”时自动回退下载源码包
- 支持从 requirements.txt 批量下载
- 支持指定目标平台（Windows/Linux/macOS）
- 自动生成离线安装用的 requirements.txt
- 自动分流源码包到 `sources/` 并生成处理指引
- 支持生成 hash 校验（安全安装）
- 支持配置文件自定义 PyPI 镜像源
- 自动生成离线安装脚本

## 安装

```bash
# 克隆项目
git clone <repository-url>
cd auto_wheel

# 安装依赖
python -m pip install -e .
```

## 快速开始

### 基本用法

```bash
# 从 requirements.txt 下载包（Python 3.9）
auto-wheel -p 3.9 -r requirements.txt

# 下载特定的包
auto-wheel -p 3.9 -pkg requests flask pandas

# 指定输出目录
auto-wheel -p 3.9 -r requirements.txt -o ./my_wheels
```

### 跨平台下载

```bash
# 在 Windows 上为 Linux 服务器下载包
auto-wheel -p 3.9 -r requirements.txt --platform manylinux2014_x86_64

# 常见平台标识：
# - Windows: win_amd64, win32
# - Linux: manylinux2014_x86_64, manylinux2014_aarch64
# - macOS: macosx_10_9_x86_64, macosx_11_0_arm64
```

### 安全安装（带 hash 校验）

```bash
# 生成带 hash 的 requirements.txt
auto-wheel -p 3.9 -r requirements.txt --with-hashes
```

## 配置文件

可以创建 `config.json` 来自定义设置（可参考 `examples/config.example.json`）：

```json
{
  "index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
  "trusted_hosts": ["pypi.tuna.tsinghua.edu.cn"],
  "extra_index_urls": [],
  "default_python_version": "3.9",
  "default_platform": "auto",
  "download_dir": "./downloads",
  "pip_timeout": 300,
  "retries": 3,
  "use_uv_resolver": true
}
```

使用配置文件：

```bash
auto-wheel -p 3.9 -r requirements.txt -c config.json
```

### 依赖解析（默认启用 uv）

`pip download --python-version` 在跨版本场景下可能无法获取条件依赖（例如 Python 3.9 + pytest 需要 `exceptiongroup`）。
配置 `"use_uv_resolver": true` 且安装 [uv](https://github.com/astral-sh/uv) 后，auto-wheel 会先运行 `uv pip compile` 生成完整依赖，再执行 `pip download`。

优点：

- 正确处理环境标记，避免条件依赖缺失。
- 解析速度更快。

未安装 uv 时，会自动回退至 pip 原始流程，并在日志中提示可能缺失条件依赖。

安装 uv 示例：

```powershell
# Windows PowerShell
irm https://astral.sh/uv/install.ps1 | iex

# macOS/Linux
curl -Ls https://astral.sh/uv/install.sh | sh
```

安装完成后执行 `uv --version` 验证即可。

### 配置说明

- `index_url`: PyPI 镜像源地址（留空使用官方源）
- `trusted_hosts`: 可信任的主机列表（使用 HTTP 源时需要）
- `extra_index_urls`: 额外的包索引地址
- `default_python_version`: 默认 Python 版本
- `default_platform`: 默认目标平台
- `download_dir`: 下载目录
- `pip_timeout`: pip 单次网络请求超时时间（秒）
- `retries`: 重试次数
- `use_uv_resolver`: 是否启用 uv pip compile 解析（默认 true）

### 常用镜像源

```json
{
  "index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
  "trusted_hosts": ["pypi.tuna.tsinghua.edu.cn"]
}
```

其他国内镜像：
- 清华：`https://pypi.tuna.tsinghua.edu.cn/simple`
- 阿里云：`https://mirrors.aliyun.com/pypi/simple/`
- 中科大：`https://pypi.mirrors.ustc.edu.cn/simple/`
- 豆瓣：`https://pypi.douban.com/simple/`

## 离线安装

下载完成后，将 `downloads` 文件夹复制到离线机器，然后：

> 重要：请先激活 `venv/conda` 虚拟环境。安装脚本会拒绝在全局 Python 环境执行。
> 若目录中存在 `sources-offline.txt`，请先按 `SOURCE_INSTALL_GUIDE.md` 处理源码包，再执行常规离线安装。

### 方法 1：使用自动生成的安装脚本

```bash
# Linux/Mac
cd downloads
./install.sh

# Windows
cd downloads
install.bat
```

> 脚本会先检查源码包清单。若检测到待处理源码包，会直接退出并提示先处理 `sources/`。

### 方法 2：使用 pip 命令

```bash
# 先确认源码包已按 SOURCE_INSTALL_GUIDE.md 处理完成
python -m pip install --no-index --find-links=downloads -r downloads/requirements-offline.txt
```

### 方法 3：安装单个包

```bash
python -m pip install --no-index --find-links=downloads package_name
```

## 命令行参数

```
输入参数（二选一）：
  -r, --requirements      requirements.txt 文件路径
  -pkg, --packages        包名列表 (空格分隔)

可选参数：
  -p, --python-version    目标 Python 版本 (如: 3.9, 3.10，留空可使用配置默认值)
  -o, --output           输出目录 (默认: ./downloads)
  -c, --config           配置文件路径
  --platform             目标平台 (如: manylinux2014_x86_64)
  --implementation       Python 实现 (默认: cp for CPython)
  --abi                  Python ABI 标签
  --only-binary          优先只下载二进制包 (默认: :all:；无 wheel 时自动回退源码下载)
  --with-hashes          生成带 hash 的 requirements.txt
  -v, --verbose          详细输出
  --dry-run              模拟运行，不实际下载
```

## 示例场景

### 场景 1：为生产服务器准备包

```bash
# 1. 在有网络的机器上下载
auto-wheel -p 3.9 -r requirements.txt --platform manylinux2014_x86_64 --with-hashes

# 2. 复制 downloads 文件夹到服务器

# 3. 如存在 sources-offline.txt，先按 SOURCE_INSTALL_GUIDE.md 处理源码包

# 4. 在服务器上安装 wheel 依赖
python -m pip install --no-index --find-links=downloads -r downloads/requirements-offline.txt
```

### 场景 2：使用私有镜像源

创建 `config.json`:

```json
{
  "index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
  "trusted_hosts": ["pypi.tuna.tsinghua.edu.cn"],
  "pip_timeout": 600
}
```

运行：

```bash
auto-wheel -p 3.9 -r requirements.txt -c config.json
```

### 场景 3：准备多个 Python 版本的包

```bash
# Python 3.9
auto-wheel -p 3.9 -r requirements.txt -o downloads/py39

# Python 3.10
auto-wheel -p 3.10 -r requirements.txt -o downloads/py310

# Python 3.11
auto-wheel -p 3.11 -r requirements.txt -o downloads/py311
```

## 技术说明

> 想了解整体架构、重试策略、GUI 方案与离线脚本细节，可参阅 `docs/TECHNICAL_OVERVIEW.md` 与 `docs/GUI_DESIGN.md`。

### 桌面 GUI（可选）

项目提供 PyQt6 + qt-material 实现的桌面客户端，覆盖常用参数配置与日志查看。

```bash
# 安装 GUI 依赖
python -m pip install -e .[gui]

# 启动客户端
auto-wheel-gui
```

核心特性：

- 纯代码构建界面，包含参数表单、日志控制台、进度展示与输出目录快捷打开。
- 集成 `qt-material`，支持亮/暗主题切换并自动记忆用户偏好。
- 行为与 CLI 完全一致，底层调用 `WheelDownloader` 与 `RequirementsGenerator`，不会影响现有命令行流程。

### 依赖解析

工具使用两阶段策略：
1) 优先通过 `uv pip compile` 按目标 Python 版本/平台解析依赖，正确处理条件依赖（如 pytest<3.11 需要 exceptiongroup/tomli）。
2) 使用 `pip download` 按解析结果下包。

当 uv 未安装（或手动配置 `use_uv_resolver:false`）时，会自动回退至 pip 直接下载流程，可能缺失跨版本条件依赖，日志会提示。

### 平台兼容性

- 纯 Python 包：会下载 `py3-none-any.whl`，适用所有平台
- 平台相关包：需要指定 `--platform` 参数
- 某些包可能没有预编译的 wheel，会下载源码包（.tar.gz 或 .zip）并放入 `sources/`
- 当首轮 wheel-only 失败且命中“无可用发行版”特征时，会自动移除 `--only-binary` 重试一次
- 若有源码包，工具会生成 `sources-offline.txt` 和 `SOURCE_INSTALL_GUIDE.md`

### 本次改动复盘（apache-iotdb）

#### 原因分析

- 仅依赖 `--only-binary :all:` 时，`apache-iotdb` 依赖链中的部分包在目标环境不存在可用 wheel，会导致 `pip download` 直接失败。
- 在 `uv` 解析结果路径下，可能出现“解析能锁定版本，但目标环境无对应发行版”的情况（例如日志中的 `greenlet` / `thrift`）。
- 即使触发源码回退，如果仍沿用目标解释器/平台约束参数，`pip` 会拒绝执行源码下载。

#### 解决思路

- 保持“wheel 优先”不变，仅在可识别的“无可用发行版”错误下触发源码回退。
- 回退阶段放宽约束（移除 `--only-binary` 与目标解释器/平台约束参数），让源码包能够落地到 `sources/`。
- 对 `uv` 路径增加兜底：当 uv 解析列表下载失败且命中“无可用发行版”特征时，自动回退到原始包列表重试。

#### 实际解决方式

- 下载器返回结构新增：
  - `used_source_fallback`：是否触发源码回退
  - `fallback_reason`：触发回退的判定原因
- CLI/GUI 新增统一提示：
  - 回退成功时明确提示先处理 `SOURCE_INSTALL_GUIDE.md`
  - 回退失败时输出分阶段线索（`wheel_only` / `source_fallback`）
- `-pkg` 场景修正为：仅 `uv` 成功时走“解析列表下载”；否则回退原始包列表下载。

> 若日志出现“`uv 解析结果下载失败，回退到原始包列表重试`”并最终成功，这是预期行为，不是错误状态。

### Hash 校验

使用 `--with-hashes` 选项会：
1. 计算每个下载包的 SHA256 hash
2. 在 requirements.txt 中包含 hash 值
3. 安装时 pip 会验证包完整性，防止篡改

## 注意事项

1. 某些包可能需要编译，确保离线环境有相应的编译工具
2. 跨平台下载时，仔细确认目标平台标识
3. 使用 `--dry-run` 预览下载操作
4. 大型项目可能下载数百个包，需要较大存储空间
5. Python 版本差异可能导致包不兼容，建议版本精确匹配

## 故障排除

### 问题：找不到某个包的 wheel

解决方案：
- 检查包是否支持目标 Python 版本
- 尝试不指定 `--platform`，让工具自动选择
- 某些包只有源码，需要在目标机器上编译
- 若看到 `wheel_only` 失败但最终 `Download completed successfully`，说明已自动回退到源码下载路径

### 问题：下载超时

解决方案：
- 增加 config.json 中的 `pip_timeout` 值
- 使用国内镜像源
- 增加 `retries` 重试次数

### 问题：离线安装失败

解决方案：
- 检查 Python 版本是否匹配
- 使用 `--with-hashes` 时确保使用完整的 requirements 文件
- 检查平台是否匹配

### 问题：安装脚本提示“检测到源码包清单”并退出

解决方案：
- 先查看 `downloads/SOURCE_INSTALL_GUIDE.md`
- 按 `downloads/sources-offline.txt` 逐个处理 `downloads/sources/` 中的源码包
- 源码包处理完成后，再执行 `python -m pip install --no-index --find-links=downloads -r downloads/requirements-offline.txt`

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
