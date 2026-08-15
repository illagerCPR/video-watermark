"""步骤 2 端到端测试：GUI 触发导出 -> 后台线程 -> 生成成品。

运行：  .venv\\Scripts\\python.exe scripts\\gui_export_test.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.main_window import MainWindow  # noqa: E402

OUT = ROOT / "outputs"
SAMPLE = OUT / "sample_video.mp4"
OUTPUT = OUT / "gui_export_test.mp4"

app = QApplication(sys.argv)
win = MainWindow()
win.show()

# 准备输入 / 输出
win.input_edit.setText(str(SAMPLE))
win.output_edit.setText(str(OUTPUT))
# 设为移动模式 + 8 字形轨迹 + 图片水印，覆盖完整路径
win.mode_combo.setCurrentIndex(1)
win.kind_combo.setCurrentIndex(1)
win.image_path_edit.setText(str(OUT / "logo.png"))
for i in range(win.trajectory_combo.count()):
    if win.trajectory_combo.itemData(i) == "figure8":
        win.trajectory_combo.setCurrentIndex(i)
        break

results = {}
state = {"done": False}
progress_max = {"done": 0, "total": 0}


def on_done(stats):
    state["done"] = True
    results["stats"] = stats


def on_error(msg):
    state["done"] = True
    results["error"] = msg


def on_progress(done, total):
    progress_max["done"] = max(progress_max["done"], done)
    progress_max["total"] = max(progress_max["total"], total)


# 触发导出
win._on_export()
if win._worker is not None:
    win._worker.done.connect(on_done)
    win._worker.error.connect(on_error)
    win._worker.progress.connect(on_progress)

    def poll():
        if not state["done"] and win._worker is not None and win._worker.isRunning():
            QTimer.singleShot(200, poll)
        else:
            app.quit()

    QTimer.singleShot(200, poll)
    app.exec()
else:
    results["error"] = "worker 未启动"

failures = []
if "error" in results:
    print("[FAIL]", results["error"])
    sys.exit(1)
if not os.path.isfile(OUTPUT):
    print("[FAIL] 输出文件未生成")
    sys.exit(1)
# 帧级进度：收到进度信号且推进到总帧数（SAMPLE 共 150 帧）
if progress_max["done"] <= 0 or progress_max["total"] <= 0:
    print("[FAIL] 未收到帧级进度信号")
    sys.exit(1)
if progress_max["done"] < progress_max["total"]:
    print(f"[FAIL] 帧进度未到达总帧数 {progress_max['done']}/{progress_max['total']}")
    sys.exit(1)
print(f"[OK] 帧级进度到达总帧数 {progress_max['done']}/{progress_max['total']}")
print(f"[OK] 导出完成: {results['stats']}")
print(f"[OK] 输出文件: {OUTPUT}  {os.path.getsize(OUTPUT)} 字节")
print("全部通过")
sys.exit(0)
