# 快速开始指南

## 1. 安装项目

```bash
cd auto_wheel
pip install -e .
```

这将安装 auto-wheel 及其依赖包。

## 2. 基础使用

### 示例 1：下载示例包

```bash
# 使用项目自带的示例 requirements.txt
auto-wheel -p 3.9 -r example_requirements.txt
```

这将下载 requests、flask、pandas、numpy 及其所有依赖到 `./downloads` 目录。

### 示例 2：下载指定的包

```bash
auto-wheel -p 3.9 -pkg requests flask
```

### 示例 3：模拟运行（不实际下载）

```bash
auto-wheel -p 3.9 -r example_requirements.txt --dry-run
```

## 3. 使用配置文件

### 创建配置文件

```bash
# 复制示例配置
cp config.example.json config.json
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

### 使用配置文件运行

```bash
auto-wheel -p 3.9 -r example_requirements.txt -c config.json
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
pip install --no-index --find-links=. -r requirements-offline.txt
```

## 5. 跨平台下载

如果要在 Windows 上为 Linux 服务器下载包：

```bash
auto-wheel -p 3.9 -r example_requirements.txt --platform manylinux2014_x86_64
```

常见平台标识：
- **Windows**: `win_amd64`, `win32`
- **Linux**: `manylinux2014_x86_64`, `manylinux2014_aarch64`
- **macOS Intel**: `macosx_10_9_x86_64`
- **macOS ARM (M1/M2)**: `macosx_11_0_arm64`

## 6. 安全安装（带 hash 校验）

```bash
auto-wheel -p 3.9 -r example_requirements.txt --with-hashes
```

这会在生成的 requirements-offline.txt 中包含每个包的 SHA256 hash，安装时会验证完整性。

## 7. 常见问题

### 如何查看帮助？

```bash
auto-wheel --help
```

### 如何查看详细输出？

```bash
auto-wheel -p 3.9 -r example_requirements.txt -v
```

### 下载到自定义目录？

```bash
auto-wheel -p 3.9 -r example_requirements.txt -o ./my_packages
```

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

# 步骤 5: 安装包
cd downloads
pip install --no-index --find-links=. -r requirements-offline.txt

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
├── config.example.json           # 配置示例
├── example_requirements.txt      # 测试用 requirements
├── pyproject.toml               # 项目配置
└── README.md                    # 完整文档
```

## 10. 下一步

- 阅读 [README.md](README.md) 了解更多高级功能
- 查看 [config.example.json](config.example.json) 了解所有配置选项
- 根据需要修改 `example_requirements.txt` 或创建自己的 requirements 文件
