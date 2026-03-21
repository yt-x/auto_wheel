# 快速开始指南

## 1. 安装项目

```bash
cd auto_wheel
python -m pip install -e .
```

这将安装 auto-wheel（CLI）及其基础依赖。

如需图形界面（PyQt6 + qt-material），请额外安装：

```bash
python -m pip install -e .[gui]
```

## 2. 基础使用

### 示例 1：下载示例包

```bash
# 使用项目提供的示例 requirements（examples/example_requirements.txt）
auto-wheel -p 3.9 -r examples/example_requirements.txt
```

这将下载 requests、flask、pandas、numpy 及其所有依赖到 `./downloads` 目录。
下载策略默认为“wheel 优先”；若首轮仅因无 wheel 失败，会自动回退下载源码包到 `sources/`。

### 示例 2：下载指定的包

```bash
auto-wheel -p 3.9 -pkg requests flask
```

### 示例 3：模拟运行（不实际下载）

```bash
auto-wheel -p 3.9 -r examples/example_requirements.txt --dry-run
```

## 3. 使用配置文件

### 创建配置文件

```bash
# 复制示例配置
cp examples/config.example.json config.json
```

### 编辑配置（可选）

如果需要使用镜像源，编辑 `config.json`：

```json
{
  "index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
  "trusted_hosts": ["pypi.tuna.tsinghua.edu.cn"],
  "default_python_version": "3.9",
  "download_dir": "./downloads"
}
```

默认情况下 `use_uv_resolver` 为 `true`，会优先使用 uv 做依赖解析；若未安装 uv，会自动回退到 pip 下载流程。

### 使用配置文件运行

```bash
auto-wheel -p 3.9 -r examples/example_requirements.txt -c config.json
```

## 4. 离线安装

下载完成后：

```bash
# 查看下载的文件
ls downloads/

# 使用生成的安装脚本
cd downloads
./install.sh          # Linux/Mac
# 或
install.bat           # Windows

# 或者使用 pip 命令
python -m pip install --no-index --find-links=. -r requirements-offline.txt
```

> 重要：请先激活 `venv/conda` 虚拟环境。`install.sh/install.bat` 会拒绝在全局 Python 环境执行，避免误装到系统环境。
> 若存在 `sources-offline.txt`，请先阅读 `SOURCE_INSTALL_GUIDE.md` 处理 `sources/` 中的源码包，再执行离线安装。
> 说明：安装脚本不会自动安装源码包，只会阻断并提示处理步骤。

### 4.1 本次场景（apache-iotdb）执行与判读

```bash
auto-wheel -pkg apache-iotdb -c config.json
```

若出现以下关键信息，表示流程正常：

- 出现多轮 `[wheel_only] ... failed`：说明 wheel-only 路径无法覆盖全部依赖。
- 出现 `Warning: uv 解析结果下载失败，回退到原始包列表重试。`：说明已触发 uv 结果兜底回退。
- 最终出现 `Download completed successfully!`：说明下载流程已收敛成功。
- 汇总中出现 `source packages=1`（或更高）：说明存在源码包，需先处理 `SOURCE_INSTALL_GUIDE.md`。

推荐验收点：

1. `downloads/sources-offline.txt` 存在且非空。
2. `downloads/SOURCE_INSTALL_GUIDE.md` 存在。
3. 安装脚本在源码包未处理前会阻断安装并给出提示。

## 5. 跨平台下载

如果要在 Windows 上为 Linux 服务器下载包：

```bash
auto-wheel -p 3.9 -r examples/example_requirements.txt --platform manylinux2014_x86_64
```

常见平台标识：
- **Windows**: `win_amd64`, `win32`
- **Linux**: `manylinux2014_x86_64`, `manylinux2014_aarch64`
- **macOS Intel**: `macosx_10_9_x86_64`
- **macOS ARM (M1/M2)**: `macosx_11_0_arm64`

## 6. 安全安装（带 hash 校验）

```bash
auto-wheel -p 3.9 -r examples/example_requirements.txt --with-hashes
```

这会在生成的 requirements-offline.txt 中包含每个包的 SHA256 hash，安装时会验证完整性。

## 7. 常见问题

### 如何查看帮助？

```bash
auto-wheel --help
```

### 如何查看详细输出？

```bash
auto-wheel -p 3.9 -r examples/example_requirements.txt -v
```

### 下载到自定义目录？

```bash
auto-wheel -p 3.9 -r examples/example_requirements.txt -o ./my_packages
```

### 出现 uv 回退提示是否异常？

不是异常。若日志显示：

- `uv 解析结果下载失败，回退到原始包列表重试。`
- 且最终为 `Download completed successfully!`

表示工具已按设计完成兜底回退。此时仍需根据 `sources-offline.txt` / `SOURCE_INSTALL_GUIDE.md` 先处理源码包，再做离线安装。

## 8. 完整工作流示例

```bash
# 步骤 1: 在有网络的机器上下载包
auto-wheel -p 3.9 -r requirements.txt --platform manylinux2014_x86_64 --with-hashes -o downloads

# 步骤 2: 打包下载的文件
tar -czf python-packages.tar.gz downloads/

# 步骤 3: 传输到离线机器
# (使用 U盘、内网传输等方式)

# 步骤 4: 在离线机器上解压
tar -xzf python-packages.tar.gz

# 步骤 5: 激活虚拟环境并安装包
# Linux/Mac:
# python -m venv .venv && source .venv/bin/activate
# Windows PowerShell:
# python -m venv .venv; .venv\Scripts\Activate.ps1

# 步骤 6: 如存在源码包，先按指引处理
# cat sources-offline.txt
# 查看 SOURCE_INSTALL_GUIDE.md

# 步骤 7: 安装 wheel 依赖
cd downloads
python -m pip install --no-index --find-links=. -r requirements-offline.txt

# 或使用脚本
./install.sh
```

## 9. 项目结构

```
auto_wheel/
├── src/
│   └── auto_wheel/
│       ├── __init__.py           # 包初始化
│       ├── main.py               # 主入口
│       ├── cli.py                # 命令行参数解析
│       ├── config.py             # 配置管理
│       ├── downloader.py         # 下载功能
│       └── requirements_generator.py  # requirements 生成
├── downloads/                    # 下载目录（自动创建）
├── examples/                     # 示例配置与 requirements
├── pyproject.toml               # 项目配置
└── README.md                    # 完整文档
```

## 10. 下一步

- 阅读 [README.md](README.md) 了解更多高级功能
- 查看 [examples/config.example.json](examples/config.example.json) 了解所有配置选项
- 根据需要修改 `examples/example_requirements.txt` 或创建自己的 requirements 文件
