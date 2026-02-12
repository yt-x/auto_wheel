@echo off
chcp 65001 >nul
REM 离线安装脚本（优先使用当前虚拟环境）
REM 由 auto-wheel 自动生成
setlocal enabledelayedexpansion

set "REQ_FILE=requirements-offline.txt"
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" >nul

set "EXIT_CODE=0"
set "PYTHON_EXE="

if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
    set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
)

if not defined PYTHON_EXE if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" (
    set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
)

if not defined PYTHON_EXE (
    for %%P in (python.exe py.exe) do (
        for /f "delims=" %%I in ('where %%P 2^>nul') do (
            set "PYTHON_EXE=%%I"
            goto :found_python
        )
    )
)

:found_python
if not defined PYTHON_EXE (
    echo 未能找到 Python，请先激活虚拟环境后再执行此脚本。
    set "EXIT_CODE=1"
    goto :finish
)

echo 使用 Python: %PYTHON_EXE%
"%PYTHON_EXE%" -m pip install --no-index --find-links=. -r "%REQ_FILE%"
if errorlevel 1 (
    echo 安装失败，请检查虚拟环境或 requirements 文件。
    set "EXIT_CODE=1"
    goto :finish
)

echo 安装完成！
set "EXIT_CODE=0"
goto :finish

:finish
popd
pause
exit /b %EXIT_CODE%
