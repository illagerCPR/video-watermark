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

        print(f"SELFTEST_OK ffmpeg={ffmpeg_exe}" if ok else "SELFTEST_FAIL",
              flush=True)
        return 0 if ok else 1

    app = QApplication(sys.argv)
    app.setApplicationName("视频水印工具")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
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
