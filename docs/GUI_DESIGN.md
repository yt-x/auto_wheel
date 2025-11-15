# Auto Wheel GUI 设计方案

## 1. 目标与约束
- **目的**：为不熟悉 CLI 的用户提供图形化界面，实现离线包下载、脚本生成与日志可视化。
- **约束**：
  - 纯代码构建 PyQt6 UI，不依赖 `.ui` 文件。
  - 外观统一使用 `qt-material`，提供**明亮/暗黑**两套主题供用户即时切换。
  - GUI 复用既有业务逻辑（`Config`、`WheelDownloader`、`RequirementsGenerator` 等），不影响 CLI 行为。
  - GUI 与 CLI 入口解耦：新增 `auto-wheel-gui` 启动脚本即可，不改现有脚本。

## 2. 依赖
| 名称 | 用途 |
| --- | --- |
| `PyQt6` | 基础 GUI 组件，提供 `QApplication/QMainWindow` 等。 |
| `qt-material` | 主题库，支持 `apply_stylesheet(app, theme='light_blue.xml')` 等配色。 |
| `qt-material` 的 `contrast`/`primaryColor` 参数 | 定制主色调（例如蓝/青），并用于光暗模式切换。 |

> 建议在 `pyproject.toml` 中新增可选依赖：`[project.optional-dependencies.gui] = ["PyQt6>=6.7", "qt-material>=2.14"]`。

## 3. 模块划分
```
src/auto_wheel/gui/
├── __init__.py
├── app.py             # QApplication 创建、qt-material 主题纾解
├── main_window.py     # QMainWindow，组合各功能面板
├── forms.py           # 纯代码表单组件（参数输入、配置卡片）
├── workers.py         # QThread/QRunnable，封装 WheelDownloader/RequirementsGenerator 调用
└── theme.py           # 主题配置、可用主题列表、切换逻辑
```

- **入口**：`auto_wheel.gui.app:run()`，新增到 `[project.scripts] auto-wheel-gui`.
- **业务复用**：`workers.py` 内直接调用 `Config`、`WheelDownloader`、`RequirementsGenerator`，保证与 CLI 一致。

## 4. UI 架构
### 4.1 布局
- `MainWindow` 继承 `QMainWindow`，`centralWidget` 使用 `QSplitter` 分为两列：
  1. **左列（参数面板）**：使用 `QTabWidget`，包含：
     - **基础参数**：Python 版本、输出目录、镜像配置、平台。
     - **依赖来源**：two radio buttons ("requirements 文件" / "包列表")，依据选择展示 `QFileDialog` 或 `QPlainTextEdit`。
     - **高级设置**：retry 次数、超时、only-binary、with-hashes。
  2. **右列（执行 & 日志）**：
     - 顶部 `QGroupBox` 展示当前状态 / 进度条（`QProgressBar`）。
     - 中部 `QPlainTextEdit` 作为日志控制台（追加 `WheelDownloader` 的 stdout/stderr）。
     - 底部按钮区：`开始下载 / 停止 / 打开输出目录 / 生成脚本`。

### 4.2 操作流
1. 用户在左侧填写参数或浏览 `requirements.txt`。
2. 点击“开始下载”后：
   - 参数面板锁定（禁用输入）。
   - 启动 `DownloadWorker`（QThread/QRunnable），内部调用 `WheelDownloader` 并通过 `Signal` 发回：
     - `progress(attempt, total)`：用于进度条。
     - `log(line)`：追加到日志窗口。
     - `finished(success, payload)`：恢复 UI 状态，如成功则提示输出目录及脚本路径。
3. 一旦完成或用户点击“停止”，恢复输入、重置进度。

## 5. 主题策略
- **主题配置** (`theme.py`):
  ```python
  AVAILABLE_THEMES = {
      "light": "light_blue.xml",
      "dark": "dark_teal.xml",
  }
  DEFAULT_PRIMARY = "#2962FF"
  DEFAULT_ACCENT = "#00BFA5"
  ```
- `app.py` 启动时：
  ```python
  from qt_material import apply_stylesheet
  apply_stylesheet(app, theme=AVAILABLE_THEMES["light"], invert_secondary=True)
  ```
- `MainWindow` 右上角放置主题切换按钮（`QComboBox` 或 `QAction`），切换时调用 `apply_stylesheet` 重新套用主题，并把偏好写入 `~/.config/auto-wheel/gui.json`。

## 6. 与现有逻辑的衔接
- `workers.DownloadWorker` 调用流程：
  ```python
  downloader = WheelDownloader(
      python_version=form.python_version(),
      output_dir=form.output_dir(),
      platform=form.platform(),
      implementation=form.implementation(),
      abi=form.abi(),
      only_binary=form.only_binary(),
      verbose=form.verbose(),
      config_pip_args=config.get_pip_args(),
      max_attempts=form.retries(),
      retry_delay=form.retry_delay(),
      command_timeout=form.timeout()
  )
  ```
- `RequirementsGenerator` 仍在下载成功后执行，不需要 UI 额外逻辑，只在 `finished` 信号中提示脚本路径。
- 所有业务异常通过 `Signal` 回传，UI 负责弹出 `QMessageBox`。

## 7. 用户体验细节
- **进度反馈**：每次 `WheelDownloader` 尝试前后发送状态，“Attempt n/m”+日志行；失败/超时在日志中标红（通过 `QTextCharFormat`）。
- **输出目录**：提供“…”按钮打开 `QFileDialog`；下载完成后可直接点击“打开目录”调用 `QDesktopServices.openUrl`.
- **包列表模式**：提供多行文本输入并提示用空行分隔；点击下载时按行拆分。
- **错误处理**：如果 `requirements.txt` 不存在或参数缺失，在 GUI 端即时提醒，不进入后台任务。

## 8. 实施步骤
1. **依赖与入口**：更新 `pyproject.toml`（可选依赖 + `auto-wheel-gui` 脚本）。
2. **代码骨架**：创建 `gui` 包与 `app.py/main_window.py/workers.py/theme.py`，完成 QApplication 初始化、主窗体布局、信号/槽。
3. **业务接入**：编写 `DownloadWorker`，在后台执行 `WheelDownloader` 并回调 UI；复用 `Config`、`RequirementsGenerator`。
4. **主题切换**：集成 `qt-material`，实现明/暗模式切换并持久化。
5. **测试 & 文档**：编写 README/TECHNICAL_OVERVIEW 中的 GUI 使用说明，补充示例截图（可选）。

## 9. 后续扩展
- 允许导入多份 requirements 形成批处理队列。
- 加入可视化的依赖树/下载列表。
- 添加“脚本测试”按钮，调用虚拟环境执行 `install.sh` 的 `--dry-run` 模式并输出日志。

该方案满足纯代码 UI、qt-material 主题、双模式外观以及逻辑复用的要求，且通过独立入口保持 CLI 兼容性。下一步可按章节 8 的顺序实施。
