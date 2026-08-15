@echo off
chcp 65001 >nul
title 视频水印工具 - 启动器
cd /d "%~dp0"

rem ---------- 检测 Python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python。请先安装 Python 3.10 或更高版本，并勾选 "Add to PATH"。
    pause
    exit /b 1
)

rem ---------- 首次运行：创建虚拟环境并安装依赖 ----------
if not exist ".venv\Scripts\python.exe" (
    echo 首次运行：正在创建虚拟环境并安装依赖，可能需要几分钟，请稍候...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败。
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
    ".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    if errorlevel 1 (
        echo [提示] 国内镜像安装失败，改用官方源重试...
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    )
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重新双击本文件。
        pause
        exit /b 1
    )
    echo 依赖安装完成。
)

rem ---------- 启动 GUI（pythonw 无控制台窗口） ----------
echo 正在启动视频水印工具...
start "" ".venv\Scripts\pythonw.exe" -m app.main
exit /b 0
