"""VideoWatermarkTUI 入口（仅 Windows；控制台子系统垫片，随 spec 打包）。

为什么需要垫片（v0.5.2）：cmd/PowerShell 启动 GUI 子系统程序
（VideoWatermark.exe）时**不等待其退出**并继续读取控制台输入，与 TUI
抢键——直接运行 `VideoWatermark.exe --tui` 会"进得去但无法操作"。
本垫片是控制台子系统程序：shell 会等待它退出；它再启动
VideoWatermark.exe --tui 并等待其退出，期间 TUI 独占键盘输入。

发布布局：VideoWatermarkTUI.exe 与 VideoWatermark.exe 同目录。
刻意不导入 app 包（保持垫片体积小、不携带 ffmpeg/Qt 等依赖）；
子进程为 GUI 子系统程序，本身不会创建控制台窗口，无需隐藏窗口封装。
"""
import os
import subprocess
import sys


def main() -> int:
    if os.name != "nt":
        print("VideoWatermarkTUI 仅用于 Windows；其他平台请运行 python -m app.tui")
        return 2

    if not getattr(sys, "frozen", False):
        # 源码运行：退化为在项目根目录调起 python -m app.tui
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.tui", *sys.argv[1:]], cwd=root)
        return proc.wait()

    # 打包运行：启动同目录的 VideoWatermark.exe --tui 并等待
    exe = os.path.join(
        os.path.dirname(os.path.abspath(sys.executable)), "VideoWatermark.exe")
    if not os.path.isfile(exe):
        print("未找到 VideoWatermark.exe；请将 VideoWatermarkTUI.exe 与其放在同一目录。",
              file=sys.stderr)
        return 2
    os.environ["VIDEO_WATERMARK_TUI_PARENT_SHIM"] = "1"
    proc = subprocess.Popen([exe, "--tui", *sys.argv[1:]])
    try:
        return proc.wait()
    except KeyboardInterrupt:
        # Ctrl+C 会被送达本垫片与 TUI；TUI 自行处理后退出，这里继续等它
        try:
            return proc.wait()
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    sys.exit(main())
