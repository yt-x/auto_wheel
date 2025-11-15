# 任务记录：Windows 批处理脚本增强
- **时间**：2025-11-15
- **问题**：用户反馈 `install.bat` 在 Windows 终端会出现中文乱码，且执行失败后窗口立即退出，无法查看错误信息。
- **解决方案**：
  1. 在批处理开头加入 `chcp 65001 >nul`，统一使用 UTF-8 编码，确保中文提示可读。
  2. 引入 `EXIT_CODE` 与 `:finish` 标签，所有失败分支设置退出码并跳转到统一的收尾逻辑，保证 `popd` 和 `pause` 始终执行，方便用户查看错误输出。
- **验证**：`python -c "import compileall; compileall.compile_file('src/auto_wheel/requirements_generator.py', quiet=1)"`。
- **影响**：仅影响自动生成的 `install.bat`，CLI/GUI 逻辑未变。成功/失败都会暂停并返回正确 exit code，终端不再闪退。**
