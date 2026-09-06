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

print("== 7. ffmpeg 二进制设置（QSettings 持久化） ==")
from PySide6.QtCore import QSettings  # noqa: E402

check("设置下拉含 3 个模式", win.ff_combo.count() == 3
      and win.ff_combo.itemData(0) == "auto"
      and win.ff_combo.itemData(1) == "internal"
      and win.ff_combo.itemData(2) == "custom")
check("默认模式为自动", win.ff_combo.currentData() == "auto")
check("默认路径输入禁用", not win.ff_path_edit.isEnabled())

# 模拟选择「内置二进制」：env 应写入 internal，QSettings 持久化
win.ff_combo.setCurrentIndex(1)
check("切内置后 env=internal",
      os.environ.get("VIDEO_WATERMARK_FFMPEG") == "internal")
s = QSettings("VideoWatermark", "VideoWatermark")
check("QSettings 已持久化 internal", str(s.value("ffmpeg/mode")) == "internal")

# 模拟自定义路径：env 写入路径，输入框启用
fake = str(ROOT / "scripts" / "gui_smoke.py")  # 存在的文件充当路径占位
win.ff_combo.setCurrentIndex(2)
win.ff_path_edit.setText(fake)
win._on_ff_path_edited()
check("切自定义后输入框启用", win.ff_path_edit.isEnabled())
check("自定义路径写入 env", os.environ.get("VIDEO_WATERMARK_FFMPEG") == fake)

# 恢复默认（auto 清空 env），并清理测试写入的 QSettings，避免污染真机设置
win.ff_combo.setCurrentIndex(0)
check("恢复自动后 env 清除", "VIDEO_WATERMARK_FFMPEG" not in os.environ)
s.remove("ffmpeg")
s.sync()

print("== 8. 硬件检测信息布局（v0.5.1 回归） ==")
# 打包后的 ffmpeg 路径很长（_MEI 临时目录），多行换行曾把文字压到相邻控件上：
# 详情现放独立整行的 hw_detail_label，且 wordWrap 标签带 heightForWidth 策略。
from PySide6.QtWidgets import QPushButton  # noqa: E402

from app.core import ffbin as _ffbin  # noqa: E402

_orig_info = _ffbin.info
_ffbin.info = lambda: {
    "exe": (r"C:\Users\illag\AppData\Local\Temp\_MEI00005be82"
            r"\imageio_ffmpeg\binaries-win-x86_64-v7.1.exe"),
    "source": "内置二进制",
}
try:
    win._detect_hw()
    app.processEvents()
    app.processEvents()
finally:
    _ffbin.info = _orig_info
_info, _detail = win.hw_info_label, win.hw_detail_label
check("检测摘要为单行", "\n" not in _info.text(), _info.text())
_need = _detail.heightForWidth(_detail.width())
check("详情行高度按换行撑开",
      _detail.isVisible() and _detail.height() >= _need,
      f"h={_detail.height()} need={_need}")
_btn = next(b for b in win.findChildren(QPushButton)
            if b.text() == "检测")
check("详情行不与按钮行重叠",
      _detail.geometry().top() >= _btn.geometry().bottom() - 1)
check("检测输出含硬件解码器报告（v0.5.3）",
      "硬件解码器" in _detail.text())

print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
sys.exit(1 if failures else 0)
