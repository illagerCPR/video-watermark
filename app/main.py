"""程序入口：启动图形界面。

运行方式：
  python -m app.main          （推荐，需在项目根目录）
  python app/main.py
"""
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.ui.main_window import MainWindow
else:
    from .ui.main_window import MainWindow


def _selftest_double(x: int) -> int:
    """供 --selftest 的进程池子进程调用（模块级才能跨进程 pickle）。"""
    return x * 2


def _apply_app_icon(app) -> None:
    """设置窗口/任务栏图标。

    开发模式读取项目根目录 icon.ico；打包（PyInstaller onefile）后从
    sys._MEIPASS 读取内嵌副本（spec 已把 icon.ico 加入 datas）。
    图标缺失或加载失败时静默跳过，不影响启动。
    """
    from PySide6.QtGui import QIcon

    try:
        base = getattr(sys, "_MEIPASS", None)
        if base:
            ico = os.path.join(base, "icon.ico")
        else:
            ico = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "icon.ico")
        if os.path.isfile(ico):
            app.setWindowIcon(QIcon(ico))
    except Exception:  # noqa: BLE001
        pass

    # Windows 任务栏：设置显式 AppUserModelID，避免任务栏/标题栏使用默认图标
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "VideoWatermark")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    from PySide6.QtWidgets import QApplication

    # 自检模式：离屏构建主窗口 + 端到端编码验证（打包完整性）
    if "--selftest" in sys.argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import shutil
        import tempfile

        from PySide6.QtWidgets import QApplication

        app = QApplication([])
        win = MainWindow()
        ok = win.windowTitle() == "视频水印工具"

        # 1) 内置 ffmpeg 二进制可用
        import imageio_ffmpeg

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ok = ok and os.path.isfile(ffmpeg_exe)

        # 2) 端到端：用内置 ffmpeg 生成短视频 -> 加水印 -> 编码输出
        from app.core.encoder import generate_sample_video, process
        from app.models import KIND_TEXT, MODE_TILED, WatermarkConfig

        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(tmp, "t.mp4")
            out = os.path.join(tmp, "o.mp4")
            generate_sample_video(src, size=(160, 90), duration=0.5, fps=15)
            process(src, out, WatermarkConfig(
                kind=KIND_TEXT, mode=MODE_TILED, text="SELFTEST"))
            ok = ok and os.path.isfile(out) and os.path.getsize(out) > 1000
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # 3) 批量并行用到的进程池在打包环境下可用：
        #    freeze_support() 保证子进程不重新弹主窗口、正常执行 worker。
        #    若缺 freeze_support，子进程会弹窗阻塞，pool.submit 失败/超时 -> 自检失败。
        import concurrent.futures

        with concurrent.futures.ProcessPoolExecutor(max_workers=1) as pool:
            ok = ok and pool.submit(_selftest_double, 21).result(timeout=60) == 42

        print(f"SELFTEST_OK ffmpeg={ffmpeg_exe}" if ok else "SELFTEST_FAIL",
              flush=True)
        return 0 if ok else 1

    app = QApplication(sys.argv)
    app.setApplicationName("视频水印工具")
    _apply_app_icon(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    # 打包（PyInstaller onefile）后，批量并行用 ProcessPoolExecutor 拉起的
    # 子进程会重新执行本入口；必须在此调用 freeze_support()，否则子进程
    # 会重复执行 main() 弹出新主窗口而不会真正跑 worker。
    # 开发模式（python -m app.main）下该调用是无副作用 no-op。
    import multiprocessing
    multiprocessing.freeze_support()

    # 启动失败时把错误写入 gui_error.log（pythonw 静默启动时也能排查）
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        import traceback
        log_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "gui_error.log")
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        print(f"启动失败，详情见 {log_path}", file=sys.stderr)
        sys.exit(1)
