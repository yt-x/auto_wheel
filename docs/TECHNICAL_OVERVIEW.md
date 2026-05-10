# Auto Wheel 技术说明（2025-11）

## 1. 系统概览
- **定位**：在联网环境批量下载第三方 Python 包、生成可校验的离线仓库及安装脚本，使内网/离线环境能快速复现依赖。
- **入口**：`auto-wheel` CLI（`src/auto_wheel/main.py`），由 `pyproject.toml` 的 `[project.scripts]` 注册。
- **目录要点**：
  - `src/auto_wheel/cli.py`：命令行解析与参数校验。
  - `src/auto_wheel/config.py`：加载 `config.json`，统一输出 pip 附加参数。
  - `src/auto_wheel/downloader.py`：封装 `pip download`，包含进程级重试、线性退避、整体超时，以及“无 wheel 自动回退源码下载”。
  - `src/auto_wheel/requirements_generator.py`：生成 `requirements-offline.txt`、`sources-offline.txt`、`SOURCE_INSTALL_GUIDE.md` 及 `install.sh/.bat`。
  - `downloads/`：执行期间生成，承载 wheel 与离线安装脚本；源码包会分流到 `downloads/sources/`。

## 2. 下载流程与稳健性
1. CLI 收集输入源（`-r` 或 `-pkg` 二选一）、`--python-version`（可选）、平台、实现等参数。
2. `Config.get_pip_args()` 依据 `config.json` 拼装 `--index-url / --trusted-host / --timeout / --retries` 等 pip 参数。
3. 依赖解析默认优先走 uv（`use_uv_resolver=true`）：
   - `-r` 输入保留原生 requirements 语义，uv 不可用时直接回退 `pip download -r <原文件>`。
   - `-pkg` 输入在 uv 成功时下载 pinned 结果，失败或不可用时回退原始包列表。
4. `WheelDownloader` 组装 `python -m pip download ...` 命令，并按两阶段执行：
   - **阶段一（wheel-only）**：保留 `--only-binary`，执行最多 `config.retries` 次（至少一次）。
   - **阶段二（source fallback）**：仅当阶段一失败且识别为“无匹配发行版/无可用版本”时触发；优先尝试直连采集 sdist，随后使用 source-only + `--no-deps` 回退命令，在目标约束下再次执行重试策略。
   - **结果标记**：返回 `used_source_fallback` 与 `fallback_reason`，供 CLI/GUI 输出统一提示。
   - 重试细节：
    - **命令级超时**：每次调用受 `max(config.pip_timeout, 60)` 秒整体限制，防止 pip 卡死。
    - **线性退避**：失败后按照 `retry_delay * attempt_index` 秒休眠（默认 3s, 6s, 9s...）。
    - **错误归类**：对 `TimeoutExpired`、`CalledProcessError`、`OSError` 打印结构化说明并保存在结果字典，方便上层提示或记日志。
5. 成功后 `RequirementsGenerator` 扫描 `downloads/`：wheel 进入 `requirements-offline.txt`，源码包分流至 `sources/` 并写入 `sources-offline.txt`，同时生成 `SOURCE_INSTALL_GUIDE.md`。
6. `generate_install_script()` 为 Linux/macOS 输出 `install.sh`、为 Windows 输出 `install.bat`：两者都只接受已激活虚拟环境（`$VIRTUAL_ENV`/`$CONDA_PREFIX` 或 `%VIRTUAL_ENV%`/`%CONDA_PREFIX%`）中的 Python；若检测到未处理源码包清单，会先阻断并提示按指引处理，避免半安装状态。
7. 可选高级流程：
   - `--plan-only`：仅输出依赖树预览与覆盖报告，不执行下载。
   - `--approve-tree <path>`：启用确认闸口，要求依赖树确认文件与当前目标参数一致。
   - `--verify-installability`：下载后执行离线可安装性预演并生成 `installability-report.md`。

## 2.1 状态模型（新增）

- **任务级状态（JobState）**：`created` / `resolving_uv` / `resolving_pip_fallback` / `planning_ready` / `downloading` / `verifying_installability` / `completed` / `completed_with_risks` / `failed`
- **依赖级状态（DependencyState）**：`pending` / `resolved` / `wheel_ready` / `source_required` / `manual_required` / `unresolved`
- **产物级状态（ArtifactState）**：`missing` / `generated` / `validated` / `invalid`

CLI 与 GUI 通过统一的解析状态快照字段输出状态变化，便于审计与回归测试。

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
| `pip_timeout` | `300` | 传入 pip `--timeout`，并作为进程级超时的下限。 |
| `retries` | `3` | pip `--retries` 及 `WheelDownloader` 进程重试次数（>=1）。 |
| `use_uv_resolver` | `true` | 是否优先使用 `uv pip compile` 解析依赖；未安装 uv 自动回退。 |

> 目前 `retry_delay` 固定 3 秒，可根据需要扩展配置字段；若将 `retries` 设为 1，则整个下载只执行一次。

## 4. 离线安装脚本行为
- **install.sh**：仅检测 `$VIRTUAL_ENV/bin/python` 或 `$CONDA_PREFIX/bin/python`；若未激活虚拟环境则拒绝执行，并给出 `python -m venv` / `source .../activate` 指引。
- **install.bat**：仅检测 `%VIRTUAL_ENV%\Scripts\python.exe` 或 `%CONDA_PREFIX%\python.exe`；若未激活虚拟环境则拒绝执行，并给出 `.venv\Scripts\Activate.ps1` / `activate.bat` 指引。
- 两个脚本默认在 `downloads/` 根目录运行，先检查 `sources-offline.txt` 是否存在待处理源码包；若存在则退出并提示先阅读 `SOURCE_INSTALL_GUIDE.md`。
- 源码包处理完成后，再执行 `python -m pip install --no-index --find-links=. -r requirements-offline.txt`，保证仅从离线介质安装且不污染全局环境。

## 5. 开发与调试建议
1. **本地测试**：`python -m pip install -e .` 安装 CLI 后执行 `auto-wheel -p 3.9 -r examples/example_requirements.txt --dry-run -v` 验证命令拼接。
2. **脚本验证**：完成一次真实下载后，先激活 `venv/conda`，再进入 `downloads/` 执行 `./install.sh` 或 `install.bat`；若存在源码包，应先验证阻断提示，再按 `SOURCE_INSTALL_GUIDE.md` 完成处理后复测。
3. **日志采集**：当前项目未内置日志文件，可在上层调用 `WheelDownloader` 结果返回值中的 `errors` 字段记录到自定义日志或 evidence。
4. **扩展点**：如需更细粒度的 retry/backoff 策略或额外配置字段，直接在 `Config.DEFAULT_CONFIG` 增加键并在 `WheelDownloader` 初始化传入即可。

## 6. 图形界面（PyQt6 + qt-material）
- **入口**：`auto-wheel-gui`，实现在 `src/auto_wheel/gui/`，主要模块：
  - `app.py`：创建 `QApplication`、应用主题并展示主窗体。
  - `main_window.py`：包含参数表单、日志面板、进度条与主题切换。
  - `forms.py`：纯代码构建输入组件，生成 `DownloadRequest`。
  - `workers.py`：封装后台线程，直接调用 `WheelDownloader` 与 `RequirementsGenerator`。
  - `theme.py`：`qt-material` 主题应用、偏好持久化。
- **依赖安装**：`python -m pip install -e .[gui]`。
- **特性**：实时日志、busy 进度条、亮/暗模式切换、输出目录快捷打开。GUI 仅为包装层，不会修改 CLI 流程。

## 6. 最新更新提示
- 2025-11-15：完成下载稳健性增强（多次尝试、线性退避、命令级超时）、离线脚本“仅虚拟环境安装”约束，以及源码包分流/阻断安装策略；请参考本说明或 `README.md` 「技术说明」章节了解行为变化。
- 2026-03-20：新增“wheel-only 失败自动源码回退”机制（仅在识别到无可用发行版时触发），并统一 CLI/GUI 的回退提示与失败分阶段线索输出。
