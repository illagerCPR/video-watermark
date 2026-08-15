"""步骤 3 测试：输出编码参数接线 + 缩放/格式端到端验证。

运行：  .venv\\Scripts\\python.exe scripts\\step3_export_test.py
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
OUTPUT = OUT / "step3_test.mov"

failures = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


app = QApplication(sys.argv)
win = MainWindow()
win.show()

print("== 1. 输出设置组默认值 ==")
check("默认格式 mp4", win.format_combo.currentData() == "mp4")
check("默认 CRF 23", win.crf_slider.value() == 23)
check("默认预设 medium", win.preset_combo.currentData() == "medium")
check("默认缩放 1.0", abs(win.scale_spin.value() - 1.0) < 1e-6)

print("== 2. 格式切换联动扩展名 ==")
win.output_edit.setText(str(OUT / "x.mp4"))
win.format_combo.setCurrentIndex(1)  # mov
check("扩展名已同步为 .mov", win.output_edit.text().endswith(".mov"))
win.format_combo.setCurrentIndex(0)  # 回 mp4
check("扩展名已同步回 .mp4", win.output_edit.text().endswith(".mp4"))

print("== 3. 端到端导出（MOV + 缩放0.5 + CRF28 + fast） ==")
win.input_edit.setText(str(SAMPLE))
win.output_edit.setText(str(OUTPUT))
win.mode_combo.setCurrentIndex(0)      # 平铺
win.kind_combo.setCurrentIndex(0)      # 文字
win.format_combo.setCurrentIndex(1)    # mov
win.crf_slider.setValue(28)
win.preset_combo.setCurrentText("fast")
win.scale_spin.setValue(0.5)

state = {"done": False}
results = {}
win._on_export()
if win._worker is not None:
    win._worker.done.connect(lambda s: (results.update(stats=s), state.update(done=True)))
    win._worker.error.connect(lambda m: (results.update(error=m), state.update(done=True)))

    def poll():
        if not state["done"] and win._worker.isRunning():
            QTimer.singleShot(200, poll)
        else:
            app.quit()

    QTimer.singleShot(200, poll)
    app.exec()
else:
    results["error"] = "worker 未启动"

if "error" in results:
    print("[FAIL]", results["error"])
    sys.exit(1)

stats = results["stats"]
check("输出尺寸按 0.5 缩放", stats["width"] == 320 and stats["height"] == 180,
      f"{stats['width']}x{stats['height']}")
check("输出文件存在", os.path.isfile(OUTPUT), f"{os.path.getsize(OUTPUT)} 字节")

# 验证文件确实为 MOV（含 mov 容器标记：读取文件头）
with open(OUTPUT, "rb") as f:
    head = f.read(32)
check("文件头为 MOV 容器", head[4:8] == b"ftyp" and b"qt" in head[:16])

OUTPUT.unlink(missing_ok=True)
print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
sys.exit(1 if failures else 0)
