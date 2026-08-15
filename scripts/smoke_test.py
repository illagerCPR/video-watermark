"""步骤 1 冒烟测试：验证轨迹与渲染逻辑（不依赖 GUI/编码）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image

from app.core import motion, watermark
from app.models import (
    KIND_IMAGE, KIND_TEXT, MODE_MOTION, MODE_TILED,
    TRAJECTORIES, WatermarkConfig,
)

failures = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not cond:
        failures.append(name)


print("== 1. 轨迹计算（6 种，坐标必须在帧内且移动） ==")
for tr in TRAJECTORIES:
    cfg = WatermarkConfig(mode=MODE_MOTION, trajectory=tr)
    bad = []
    positions = set()
    for t in [x * 0.2 for x in range(41)]:  # 0~8s
        x, y = motion.position_at(cfg, t, 640, 360, 100, 50)
        positions.add((round(x), round(y)))
        if x < -0.5 or y < -0.5 or x > 640.5 or y > 360.5:
            bad.append((t, round(x, 1), round(y, 1)))
    check(f"轨迹 {tr} 坐标在帧内", not bad, str(bad) if bad else "")
    check(f"轨迹 {tr} 确实在移动", len(positions) >= 5, f"{len(positions)} 个不同位置")

print("== 2. 文字水印渲染（多行 + 旋转 + 平铺） ==")
cfg = WatermarkConfig(kind=KIND_TEXT, mode=MODE_TILED,
                      text="机密文件\n请勿外传", font_size=42, angle=30.0)
cell = watermark.render_cell(cfg, 640, 360)
check("多行文字单元格已生成", cell.width > 0 and cell.height > 0, f"size={cell.size}")
tile = watermark.make_tile(cfg, 640, 360)
bbox = tile.getbbox()
check("平铺瓦片与帧等大", tile.size == (640, 360), f"size={tile.size}")
check("平铺瓦片有内容", bbox is not None, f"bbox={bbox}")

print("== 3. 图片水印渲染（缩放 + 圆角 + 平铺） ==")
out_dir = ROOT / "outputs"
out_dir.mkdir(exist_ok=True)
logo = out_dir / "_smoke_logo.png"
Image.new("RGBA", (120, 80), (255, 0, 0, 255)).save(logo)
cfg2 = WatermarkConfig(kind=KIND_IMAGE, image_path=str(logo), mode=MODE_TILED,
                       img_scale=0.2, img_radius=12, angle=15.0)
cell2 = watermark.render_cell(cfg2, 640, 360)
check("图片单元格按帧宽比例缩放", cell2.width == 128, f"width={cell2.width} (期望 128)")
tile2 = watermark.make_tile(cfg2, 640, 360)
check("图片平铺瓦片已生成", tile2.getbbox() is not None)

print("== 4. 移动模式单元格（按 motion_scale 比例） ==")
cfg3 = WatermarkConfig(kind=KIND_TEXT, mode=MODE_MOTION, text="© 2025",
                       motion_scale=0.18)
cell3 = watermark.render_cell(cfg3, 640, 360)
check("移动文字按比例缩放", 100 <= cell3.width <= 130, f"width={cell3.width}")

logo.unlink(missing_ok=True)
print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
sys.exit(1 if failures else 0)
