"""子进程启动封装：Windows 上隐藏控制台窗口（避免 GUI 程序一闪而过命令窗）。

打包为无控制台的 GUI exe（PySide6 + PyInstaller console=False / pythonw）后，
直接 subprocess 拉起 ffmpeg / explorer 会短暂弹出一个黑色控制台窗口
（CREATE_NO_WINDOW 未设置时新进程继承控制台创建标志）。所有子进程启动统一
经本模块的 run() / popen()，在 Windows 上自动附加 CREATE_NO_WINDOW 隐藏窗口。

注意：imageio-ffmpeg 内部的 ffmpeg 进程已自带窗口隐藏，无需（也不应）经此封装。
"""
from __future__ import annotations

import os
import subprocess

# CREATE_NO_WINDOW = 0x08000000：新进程不创建控制台窗口（GUI 程序必需）。
# 非 Windows 平台传 0（无副作用）。
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def run(args, **kwargs):
    """隐藏窗口地执行子进程并等待（等价 subprocess.run）。"""
    kwargs.setdefault("creationflags", _CREATE_NO_WINDOW)
    return subprocess.run(args, **kwargs)


def popen(args, **kwargs):
    """隐藏窗口地启动子进程（等价 subprocess.Popen）。"""
    kwargs.setdefault("creationflags", _CREATE_NO_WINDOW)
    return subprocess.Popen(args, **kwargs)


__all__ = ["run", "popen"]
