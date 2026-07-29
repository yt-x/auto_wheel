# Auto Wheel

Auto Wheel 是一个用于准备 Python 离线安装包的工具。它会根据目标 Python
版本、平台和依赖输入下载 wheel 包，生成离线安装所需的 requirements 文件、
安装脚本、源码包处理指引和可选校验报告。

当前实现同时提供命令行工具和桌面 GUI：

- CLI：`auto-wheel`
- GUI：`auto-wheel-gui`

## 主要能力

- 从 `requirements.txt`、包名列表或项目目录自动识别依赖来源。
- 支持读取 `pyproject.toml` 的 `project.dependencies`。
- 支持读取 TOML lock 文件中的 registry 包，并跳过 git / directory 等非 registry 来源。
- 默认优先使用 `uv pip compile` 解析目标环境依赖。
- 未安装 uv、uv 失败或禁用 uv 时，保留 pip 原始下载流程。
- 支持目标 Python 版本、平台、实现和 ABI 参数。
- 默认 wheel 优先下载；仅在识别到无可用 wheel / 发行版时，自动回退下载源码包。
- 自动把源码包分流到 `sources/`，并生成 `sources-offline.txt` 与 `SOURCE_INSTALL_GUIDE.md`。
- 生成离线安装清单 `requirements-offline.txt`，支持 hash 校验。
- 生成 `install.sh` 和 `install.bat`。
- 支持依赖预览模式，生成 `dependency-tree.json`、`dependency-tree.txt` 和 `coverage-report.md`。
- 支持确认闸口输入 `--approve-tree`。
- 支持下载后离线可安装性预演，生成 `installability-report.md`。
- 支持 PyQt6 + qt-material 桌面 GUI。

## 安装

```powershell
python -m pip install -e .
```

安装 GUI 依赖：

```powershell
python -m pip install -e ".[gui]"
```

项目要求 Python `>=3.8`。

基础依赖来自 `pyproject.toml`：

- `pip>=21.0`
- `packaging>=21.0`
- `tqdm>=4.62.0`

## 快速开始

从 requirements 文件下载：

```powershell
auto-wheel -p 3.9 -r requirements.txt
```

下载指定包：

```powershell
auto-wheel -p 3.9 -pkg requests flask pandas
```

指定输出目录：

```powershell
auto-wheel -p 3.9 -r requirements.txt -o .\downloads-py39
```

从项目目录自动识别依赖来源：

```powershell
auto-wheel -p 3.9 --from .\my-project
```

直接指定依赖来源文件：

```powershell
auto-wheel -p 3.9 --from .\my-project\uv.lock
auto-wheel -p 3.9 --from .\my-project\pyproject.toml
auto-wheel -p 3.9 --from .\my-project\requirements.txt
```

模拟运行，不实际下载：

```powershell
auto-wheel -p 3.9 -pkg requests --dry-run
```

## 依赖输入方式

CLI 的输入源三选一：

```text
-r, --requirements <file>     读取 requirements.txt
-pkg, --packages <items...>   直接传入包名或版本约束
--from <path>                 自动识别文件或目录中的依赖来源
```

`--from` 支持：

- TOML lock 文件：读取 `package` 列表中的 registry 依赖，生成 `name==version`。
- `pyproject.toml`：读取 `[project] dependencies`。
- requirements 文本文件：按 requirements 行读取。
- 目录：扫描目录下的普通文件，选择优先级最高的可识别依赖源。

目录自动识别的优先级是：

```text
lock file > pyproject.toml > requirements.txt
```

注意：

- lock 文件被视为已锁定依赖，下载时跳过二次依赖解析。
- `pyproject.toml` 和 requirements 输入会优先尝试 uv 解析。
- lock 文件中的 git、directory 等非 registry 来源会被跳过，并在日志中提示。

## 目标环境参数

常用参数：

```powershell
auto-wheel -p 3.9 -r requirements.txt --platform manylinux2014_x86_64
```

可配置项：

```text
-p, --python-version   目标 Python 版本，例如 3.9、3.10、3.11
--platform             目标平台，例如 win_amd64、manylinux2014_x86_64、macosx_11_0_arm64
--implementation       Python 实现，默认 cp
--abi                  Python ABI；未传入时根据 Python 版本自动推断
--only-binary          wheel 优先策略，默认 :all:
```

常见平台值：

- Windows x64：`win_amd64`
- Windows x86：`win32`
- Linux x64：`manylinux2014_x86_64`
- Linux ARM64：`manylinux2014_aarch64`
- macOS Intel：`macosx_10_9_x86_64`
- macOS Apple Silicon：`macosx_11_0_arm64`

## 配置文件

可以通过 `-c/--config` 指定 JSON 配置文件：

```powershell
auto-wheel -p 3.9 -r requirements.txt -c config.json
```

配置示例：

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

字段说明：

- `index_url`：主包索引地址；空字符串表示使用 pip 默认源。
- `trusted_hosts`：传给 pip 的 `--trusted-host`。
- `extra_index_urls`：额外包索引地址。
- `default_python_version`：未传 `-p` 时使用的默认 Python 版本。
- `default_platform`：未传 `--platform` 时使用的默认平台，默认 `auto`。
- `download_dir`：未传 `-o` 时使用的输出目录。
- `pip_timeout`：pip 单次网络请求超时时间，单位秒。
- `retries`：pip 重试次数，同时用于下载器最大尝试次数。
- `use_uv_resolver`：是否优先启用 uv 依赖解析。

如果不显式指定配置文件，工具按以下顺序查找，命中的第一个文件生效：

```text
-c/--config 指定 > 当前目录 ./config.json > 用户级配置 > 程序内置默认值
```

用户级配置路径：

- Windows：`%APPDATA%\auto_wheel\config.json`
- Linux / macOS：`$XDG_CONFIG_HOME/auto_wheel/config.json`（默认 `~/.config/auto_wheel/config.json`）

任何位置都找不到配置文件时，使用程序内置默认值。CLI 参数和 GUI 表单中
显式给出的值（如 `-p`、`-o`、`--platform`、重试次数、超时）优先级始终
高于配置文件。

## uv 解析与 pip 回退

默认配置 `use_uv_resolver=true`。当系统能找到 `uv` 时，Auto Wheel 会先执行
`uv pip compile`，为目标 Python 版本和目标平台生成更完整的依赖列表。

uv 解析成功时：

- 下载阶段使用 uv 解析出的锁定依赖列表。
- 离线清单进入 `lock` 模式。

uv 不可用、解析失败或配置禁用时：

- 工具回退到 pip 原始输入流程。
- requirements 文件会直接透传给 `pip download -r`。
- 包名列表和 `pyproject.toml` 依赖会按原始列表下载。
- 离线清单通常进入 `non_lock` 模式。

CLI 和 GUI 都会输出解析状态，便于判断当前使用的是 uv 还是 pip 回退路径。

## wheel 优先与源码回退

默认下载策略是 wheel 优先：

```text
--only-binary :all:
```

下载器先执行 wheel-only 下载。只有当错误文本被识别为“无可用 wheel / 无匹配发行版”
并通过探测确认后，才会进入源码回退流程。

源码回退成功时，输出目录会包含：

```text
downloads/
  *.whl
  requirements-offline.txt
  manifest-reconciliation.json
  install.sh
  install.bat
  sources/
    *.tar.gz / *.zip
  sources-offline.txt
  SOURCE_INSTALL_GUIDE.md
  source-fallback-report.json
```

如果存在源码包，离线机器上需要先阅读 `SOURCE_INSTALL_GUIDE.md`，处理
`sources/` 中的源码包，再安装常规 wheel 依赖。

安装脚本会检查源码包清单；如果发现未处理的源码包，会阻断安装并提示先处理源码包。

## 依赖预览与确认

仅生成依赖预览，不执行下载：

```powershell
auto-wheel -p 3.9 -pkg requests==2.31.0 --plan-only -o .\preview
```

生成文件：

```text
preview/
  dependency-tree.json
  dependency-tree.txt
  coverage-report.md
```

基于已确认的依赖树继续下载：

```powershell
auto-wheel -p 3.9 -pkg requests==2.31.0 --approve-tree .\preview\dependency-tree.json -o .\downloads
```

约束：

- `--plan-only` 和 `--approve-tree` 不能同时使用。
- `--approve-tree` 指向的文件必须存在。
- 确认文件中的目标 Python 和平台需要与当前命令匹配。

## 离线清单模式

下载完成后，`requirements-offline.txt` 会标注 manifest 模式。

`lock` 模式：

- 有 resolver 锁定依赖列表。
- 离线 requirements 直接来自锁定列表。
- 版本一致性更强。

`non_lock` 模式：

- 没有锁定依赖列表。
- 离线 requirements 通过扫描输出目录中的 wheel 推断生成。
- 如果复用旧输出目录，历史残留文件可能影响结果。

建议生产任务使用独立输出目录，并尽量保证 uv 可用，以获得 `lock` 模式清单。

每次生成清单都会生成：

```text
manifest-reconciliation.json
```

对账报告会记录：

- 锁定清单中缺失的产物。
- 仅有源码包的依赖。
- 输出目录中存在但不在锁定清单里的额外产物。

## hash 校验

生成带 hash 的离线 requirements：

```powershell
auto-wheel -p 3.9 -r requirements.txt --with-hashes
```

当 wheel 文件存在时，`requirements-offline.txt` 会写入对应的 SHA256 hash。
离线安装时 pip 会校验文件完整性。

## 离线可安装性预演

下载后执行离线安装预演：

```powershell
auto-wheel -p 3.9 -r requirements.txt --verify-installability -o .\downloads
```

工具会生成：

```text
downloads/installability-report.md
```

如果预演失败，CLI 退出码为 `2`，并提示查看报告。

## 离线安装

将输出目录复制到离线机器后，先激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows：

```powershell
cd downloads
.\install.bat
```

Linux / macOS：

```bash
cd downloads
./install.sh
```

也可以直接使用 pip：

```powershell
python -m pip install --no-index --find-links=downloads -r downloads\requirements-offline.txt
```

重要：

- 不要在全局 Python 环境中执行离线安装。
- 如果存在 `sources-offline.txt`，先按 `SOURCE_INSTALL_GUIDE.md` 处理源码包。
- 处理完源码包后，再安装 `requirements-offline.txt` 中的 wheel 依赖。

## GUI

安装 GUI 依赖后启动：

```powershell
python -m pip install -e ".[gui]"
auto-wheel-gui
```

GUI 支持：

- requirements、包名列表、自动识别来源三种输入模式。
- Python 版本、平台、实现、ABI、输出目录和配置文件设置。
- dry-run、hash、verbose、预览模式。
- 依赖树确认闸口。
- 下载日志、完成状态和输出目录快捷打开。
- qt-material 主题切换与偏好保存。

GUI 后台线程复用 CLI 的核心模块：

- `WheelDownloader`
- `DependencyResolver`
- `RequirementsGenerator`
- `SourceReader`

## 命令行参数摘要

```text
输入源（三选一）:
  -r, --requirements FILE
  -pkg, --packages PACKAGE [PACKAGE ...]
  --from PATH

目标环境:
  -p, --python-version VERSION
  --platform PLATFORM
  --implementation IMPLEMENTATION
  --abi ABI

输出与配置:
  -o, --output DIR
  -c, --config FILE

行为开关:
  --only-binary VALUE
  --with-hashes
  --dry-run
  --plan-only
  --approve-tree FILE
  --verify-installability
  -v, --verbose
```

查看完整帮助：

```powershell
auto-wheel --help
```

## 项目结构

```text
auto_wheel/
  pyproject.toml
  QUICKSTART.md
  README.md
  src/
    auto_wheel/
      __init__.py
      main.py
      cli.py
      config.py
      resolver.py
      downloader.py
      requirements_generator.py
      source_reader.py
      state_model.py
      approval_gate.py
      inspector.py
      utils.py
      gui/
        __init__.py
        app.py
        forms.py
        main_window.py
        theme.py
        workers.py
  tests/
    test_approval_gate.py
    test_downloader_fallback.py
    test_gui_worker_manifest_mode.py
    test_installability_check.py
    test_legacy_regression_fixtures.py
    test_main_verify_exit.py
    test_manifest_generation.py
    test_preview_and_cli.py
    test_resolver.py
    test_source_reader.py
    test_state_model.py
```

核心模块职责：

- `main.py`：CLI 主流程编排。
- `cli.py`：参数定义与校验。
- `config.py`：配置读取与 pip 参数生成。
- `resolver.py`：uv 依赖解析与 pip 回退状态管理。
- `downloader.py`：pip download、重试、wheel-only、源码回退。
- `requirements_generator.py`：离线清单、安装脚本、预览和校验报告生成。
- `source_reader.py`：`--from` 依赖来源识别。
- `state_model.py`：任务、依赖和产物状态模型。
- `approval_gate.py`：依赖树确认闸口判断。
- `inspector.py`：包元数据与 wheel 兼容性检查。
- `gui/`：PyQt6 桌面界面。

## 开发与测试

安装项目：

```powershell
python -m pip install -e .
```

运行全部测试：

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

运行单个测试文件：

```powershell
python -m unittest tests.test_resolver -v
python -m unittest tests.test_manifest_generation -v
python -m unittest tests.test_downloader_fallback -v
```

测试覆盖重点：

- CLI 参数校验、预览模式和确认闸口。
- uv 解析成功、不可用、失败分类和 pip 回退状态。
- wheel-only 成功、无 wheel 源码回退、回退失败摘要。
- lock / non_lock 清单生成和 hash 保留。
- SourceReader 对 lock、pyproject、requirements、目录扫描的处理。
- 离线可安装性预演报告与失败退出码。
- GUI worker 对 manifest lock 依赖的透传。

## 常见问题

### 未安装 uv 会失败吗？

不会。默认会提示 uv 不可用，然后回退到 pip 原始流程。但跨 Python 版本或平台解析时，
pip 原始流程可能不如 uv 完整。

### 为什么出现 non_lock 模式？

通常是因为没有 resolver 锁定依赖列表，例如 uv 不可用或解析失败。此时清单从下载目录
扫描 wheel 文件生成。建议使用独立输出目录，避免历史残留影响结果。

### 出现源码包后能直接离线安装吗？

不能直接忽略。需要先查看 `SOURCE_INSTALL_GUIDE.md` 和 `sources-offline.txt`，处理
`sources/` 中的源码包，再安装常规 wheel 依赖。

### `--plan-only` 会判断 wheel 是否可用吗？

不会。预览阶段只记录依赖解析结果，`wheel_ready`、`source_required` 等状态要到下载阶段
才能确认。

### `--approve-tree` 和 `--plan-only` 能一起使用吗？

不能。先运行 `--plan-only` 生成依赖树，再用新的命令传入 `--approve-tree` 执行下载。

## License

MIT License
