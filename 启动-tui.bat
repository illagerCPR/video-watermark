@echo off
rem 视频水印工具 - TUI 模式启动器（v0.5.0 起）
rem 需先运行过 启动.bat 完成虚拟环境初始化；后续在此终端内交互使用。
setlocal
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
    echo [启动] 未找到虚拟环境，请先双击 启动.bat 完成首次初始化。
    pause
    exit /b 1
)
set PYTHONIOENCODING=utf-8
echo [启动] 视频水印工具（TUI 模式）
.venv\Scripts\python.exe -m app.tui %*
if errorlevel 1 pause
