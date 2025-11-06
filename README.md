# Auto Wheel

自动下载 Python wheel 包至本地，用于离线环境安装。

## 功能特性

- 自动下载指定 Python 版本的 wheel 包及其所有依赖
- 支持从 requirements.txt 批量下载
- 支持指定目标平台（Windows/Linux/macOS）
- 自动生成离线安装用的 requirements.txt
- 支持生成 hash 校验（安全安装）
- 支持配置文件自定义 PyPI 镜像源
- 自动生成离线安装脚本

## 安装

```bash
# 克隆项目
git clone <repository-url>
cd auto_wheel

# 安装依赖
pip install -e .
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

可以创建 `config.json` 来自定义设置：

```json
{
  "index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
  "trusted_hosts": ["pypi.tuna.tsinghua.edu.cn"],
  "extra_index_urls": [],
  "default_python_version": "3.9",
  "default_platform": "auto",
  "download_dir": "./downloads",
  "timeout": 300,
  "retries": 3
}
```

使用配置文件：

```bash
auto-wheel -p 3.9 -r requirements.txt -c config.json
```

### 配置说明

- `index_url`: PyPI 镜像源地址（留空使用官方源）
- `trusted_hosts`: 可信任的主机列表（使用 HTTP 源时需要）
- `extra_index_urls`: 额外的包索引地址
- `default_python_version`: 默认 Python 版本
- `default_platform`: 默认目标平台
- `download_dir`: 下载目录
- `timeout`: 下载超时时间（秒）
- `retries`: 重试次数

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

### 方法 1：使用自动生成的安装脚本

```bash
# Linux/Mac
cd downloads
./install.sh

# Windows
cd downloads
install.bat
```

### 方法 2：使用 pip 命令

```bash
pip install --no-index --find-links=downloads -r downloads/requirements-offline.txt
```

### 方法 3：安装单个包

```bash
pip install --no-index --find-links=downloads package_name
```

## 命令行参数

```
必需参数：
  -p, --python-version    目标 Python 版本 (如: 3.9, 3.10)
  -r, --requirements      requirements.txt 文件路径
  -pkg, --packages        包名列表 (空格分隔)

可选参数：
  -o, --output           输出目录 (默认: ./downloads)
  -c, --config           配置文件路径
  --platform             目标平台 (如: manylinux2014_x86_64)
  --implementation       Python 实现 (默认: cp for CPython)
  --abi                  Python ABI 标签
  --only-binary          只下载二进制包 (默认: :all:)
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

# 3. 在服务器上安装
pip install --no-index --find-links=downloads -r downloads/requirements-offline.txt
```

### 场景 2：使用私有镜像源

创建 `config.json`:

```json
{
  "index_url": "https://pypi.tuna.tsinghua.edu.cn/simple",
  "trusted_hosts": ["pypi.tuna.tsinghua.edu.cn"],
  "timeout": 600
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

### 依赖解析

工具使用 `pip download` 来解析和下载依赖包，会自动处理：
- 传递依赖（依赖的依赖）
- 版本约束和冲突
- 平台特定的依赖
- 可选依赖（extras）

### 平台兼容性

- 纯 Python 包：会下载 `py3-none-any.whl`，适用所有平台
- 平台相关包：需要指定 `--platform` 参数
- 某些包可能没有预编译的 wheel，会下载源码包（.tar.gz 或 .zip）

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

### 问题：下载超时

解决方案：
- 增加 config.json 中的 `timeout` 值
- 使用国内镜像源
- 增加 `retries` 重试次数

### 问题：离线安装失败

解决方案：
- 检查 Python 版本是否匹配
- 使用 `--with-hashes` 时确保使用完整的 requirements 文件
- 检查平台是否匹配

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
