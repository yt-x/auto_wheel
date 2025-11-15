# Auto Wheel 技术说明（2025-11）

## 1. 系统概览
- **定位**：在联网环境批量下载第三方 Python 包、生成可校验的离线仓库及安装脚本，使内网/离线环境能快速复现依赖。
- **入口**：`auto-wheel` CLI（`src/auto_wheel/main.py`），由 `pyproject.toml` 的 `[project.scripts]` 注册。
- **目录要点**：
  - `src/auto_wheel/cli.py`：命令行解析与参数校验。
  - `src/auto_wheel/config.py`：加载 `config.json`，统一输出 pip 附加参数。
  - `src/auto_wheel/downloader.py`：封装 `pip download`，新增进程级重试、线性退避与整体超时。
  - `src/auto_wheel/requirements_generator.py`：生成 `requirements-offline.txt` 及 `install.sh/.bat`。
  - `downloads/`：执行期间生成，承载 wheel/sdist、离线 requirements 与脚本。

## 2. 下载流程与稳健性
1. CLI 收集 `--python-version`、输入源（`-r` 或 `-pkg`）、平台、实现等参数。
2. `Config.get_pip_args()` 依据 `config.json` 拼装 `--index-url / --trusted-host / --timeout / --retries` 等 pip 参数。
3. `WheelDownloader` 组装 `python -m pip download ...` 命令，并执行最多 `config.retries` 次（至少一次）：
   - **命令级超时**：每次调用受 `max(config.timeout, 60)` 秒整体限制，防止 pip 卡死。
   - **线性退避**：失败后按照 `retry_delay * attempt_index` 秒休眠（默认 3s, 6s, 9s...）。
   - **错误归类**：对 `TimeoutExpired`、`CalledProcessError`、`OSError` 打印结构化说明并保存在结果字典，方便上层提示或记日志。
4. 成功后 `RequirementsGenerator` 扫描 `downloads/`，输出精确版本锁定的 `requirements-offline.txt`，可选 `--with-hashes` 生成 SHA256。
5. `generate_install_script()` 为 Linux/macOS 输出 `install.sh`（自动探测 `$VIRTUAL_ENV`/`$CONDA_PREFIX`），为 Windows 输出 `install.bat`，均统一执行 `python -m pip install ...` 并在找不到解释器时立即失败。

> **提示**：CLI 的 `--dry-run` 仍仅构建命令，不触发下载逻辑；若需要进一步调试，可结合 `-v` 查看每次尝试与等待周期。

## 3. 配置字段（`config.json`）
| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `index_url` | `""` | 主 PyPI/镜像源；为空取 `https://pypi.org/simple`。 |
| `trusted_hosts` | `[]` | pip `--trusted-host` 列表（HTTP 源需要）。 |
| `extra_index_urls` | `[]` | 额外镜像。 |
| `default_python_version` | `3.9` | CLI 未显式传参时使用。 |
| `default_platform` | `auto` | 透传给 `WheelDownloader`。 |
| `download_dir` | `./downloads` | 输出目录。 |
| `timeout` | `300` | 传入 pip `--timeout`，并作为进程级超时的下限。 |
| `retries` | `3` | pip `--retries` 及 `WheelDownloader` 进程重试次数（>=1）。 |

> 目前 `retry_delay` 固定 3 秒，可根据需要扩展配置字段；若将 `retries` 设为 1，则整个下载只执行一次。

## 4. 离线安装脚本行为
- **install.sh**：优先使用 `$VIRTUAL_ENV/bin/python`，退化到 `$CONDA_PREFIX/bin/python`、`python3`、`python`；找不到解释器会阻止安装。
- **install.bat**：检测 `%VIRTUAL_ENV%\Scripts\python.exe`、`%CONDA_PREFIX%\python.exe`，最后遍历 `python.exe`/`py.exe`。每一步都使用 `python -m pip`，失败时退出并恢复目录。
- 两个脚本默认在 `downloads/` 根目录运行，结合 `requirements-offline.txt`，执行 `--no-index --find-links=.` 保证仅从离线介质安装。

## 5. 开发与调试建议
1. **本地测试**：`pip install -e .` 安装 CLI 后执行 `auto-wheel -p 3.9 -r examples/example_requirements.txt --dry-run -v` 验证命令拼接。
2. **脚本验证**：完成一次真实下载后，进入 `downloads/` 执行 `./install.sh --dry-run`（可暂改 pip 命令）或在 Windows 上运行 `install.bat`，确认虚拟环境探测逻辑。
3. **日志采集**：当前项目未内置日志文件，可在上层调用 `WheelDownloader` 结果返回值中的 `errors` 字段记录到自定义日志或 evidence。
4. **扩展点**：如需更细粒度的 retry/backoff 策略或额外配置字段，直接在 `Config.DEFAULT_CONFIG` 增加键并在 `WheelDownloader` 初始化传入即可。

## 6. 图形界面（PyQt6 + qt-material）
- **入口**：`auto-wheel-gui`，实现在 `src/auto_wheel/gui/`，主要模块：
  - `app.py`：创建 `QApplication`、应用主题并展示主窗体。
  - `main_window.py`：包含参数表单、日志面板、进度条与主题切换。
  - `forms.py`：纯代码构建输入组件，生成 `DownloadRequest`。
  - `workers.py`：封装后台线程，直接调用 `WheelDownloader` 与 `RequirementsGenerator`。
  - `theme.py`：`qt-material` 主题应用、偏好持久化。
- **依赖安装**：`pip install -e .[gui]`。
- **特性**：实时日志、busy 进度条、亮/暗模式切换、输出目录快捷打开。GUI 仅为包装层，不会修改 CLI 流程。

## 6. 最新更新提示
- 2025-11-15：完成下载稳健性增强（多次尝试、线性退避、命令级超时）与离线脚本虚拟环境支持；请参考本说明或 `README.md` 「技术说明」章节了解行为变化。
