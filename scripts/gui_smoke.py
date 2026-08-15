"""步骤 2 冒烟测试：GUI 离屏构建 + 配置收集 + 模式联动 + 预览/轨迹渲染。

运行：  .venv\\Scripts\\python.exe scripts\\gui_smoke.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.models import (  # noqa: E402
    KIND_IMAGE, KIND_TEXT, MODE_MOTION, MODE_TILED,
    TRAJECTORY_CIRCLE, TRAJECTORY_FIGURE8, WatermarkConfig,
)
from app.ui.main_window import MainWindow  # noqa: E402

failures = []
OUT = ROOT / "outputs"
SAMPLE = OUT / "sample_video.mp4"
LOGO = OUT / "logo.png"


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


app = QApplication(sys.argv)
win = MainWindow()
win.show()

check("主窗口构建成功", win.windowTitle() == "视频水印工具")

print("== 1. 默认配置收集（平铺·文字） ==")
cfg = win._cfg_from_ui()
check("默认模式为平铺", cfg.mode == MODE_TILED)
check("默认来源为文字", cfg.kind == KIND_TEXT)
check("默认角度=30", abs(cfg.angle - 30.0) < 1e-6)
check("多行文本保留", "\n" in cfg.text)
check("平铺面板可见", win.tiled_box.isVisible() and not win.motion_box.isVisible())
check("文字面板可见", win.text_box.isVisible() and not win.image_box.isVisible())

print("== 2. 模式联动 ==")
win.mode_combo.setCurrentIndex(1)  # 移动
check("切到移动后平铺隐藏", not win.tiled_box.isVisible() and win.motion_box.isVisible())
cfg = win._cfg_from_ui()
check("配置模式为移动", cfg.mode == MODE_MOTION)
check("默认轨迹为水平", cfg.trajectory == "horizontal")

print("== 3. 来源联动 ==")
win.kind_combo.setCurrentIndex(1)  # 图片
check("切到图片后文字面板隐藏", not win.text_box.isVisible() and win.image_box.isVisible())
win.image_path_edit.setText(str(LOGO))
cfg = win._cfg_from_ui()
check("配置来源为图片", cfg.kind == KIND_IMAGE)
check("图片路径已收集", cfg.image_path == str(LOGO))

print("== 4. 预览帧渲染 ==")
win.mode_combo.setCurrentIndex(0)  # 平铺
win.kind_combo.setCurrentIndex(0)  # 文字
win.input_edit.setText(str(SAMPLE))
img = win._cfg_from_ui() and __import__("app.core.preview", fromlist=["x"]).render_preview_frame(str(SAMPLE), win._cfg_from_ui(), 1.0)
check("预览帧已渲染", img is not None and img.width > 0, f"size={img.size if img else None}")

print("== 5. 轨迹示意图 ==")
win.mode_combo.setCurrentIndex(1)
win.trajectory_combo.setCurrentIndex(0)
# 切到圆周轨迹
for i in range(win.trajectory_combo.count()):
    if win.trajectory_combo.itemData(i) == TRAJECTORY_CIRCLE:
        win.trajectory_combo.setCurrentIndex(i)
preview = __import__("app.core.preview", fromlist=["x"])
sk = preview.sketch_trajectory(win._cfg_from_ui(), 640, 360)
check("轨迹示意图已渲染", sk is not None and sk.width == 640)

print("== 6. 配置构建为 JSON ==")
from app.models import config_to_json
j = config_to_json(win._cfg_from_ui())
check("配置可序列化", '"trajectory"' in j)

print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
sys.exit(1 if failures else 0)
