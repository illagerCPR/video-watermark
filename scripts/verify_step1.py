"""步骤 1 验证脚本：用像素对比客观验证水印已叠加、且移动水印确实在移动。

原理：
- 平铺：成品帧 与 同时间原片帧 应存在显著差异（半透明白色文字叠在彩色底上）
- 移动：不同时刻的水印包围盒位置不同 => 轨迹生效
"""
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
sys.path.insert(0, str(ROOT))

failures = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


def grab(video: str, t: float, fps: float = 30.0) -> Image.Image:
    """按精确帧索引读取视频第 round(t*fps) 帧（保证源/成品同帧对齐）。"""
    gen = imageio_ffmpeg.read_frames(str(OUT / video), pix_fmt="rgb24")
    meta = next(gen)  # 元数据 dict
    w, h = meta["size"]
    idx = int(round(t * fps))
    frame = None
    for i, fb in enumerate(gen):
        if i == idx:
            frame = Image.frombytes("RGB", (w, h), fb)
            break
    gen.close()
    if frame is None:
        raise RuntimeError(f"帧 {idx} 超出 {video} 范围")
    return frame


def diff_stats(a: Image.Image, b: Image.Image):
    """返回 (均差, 差异像素数, 差异包围盒)。"""
    pa, pb = a.load(), b.load()
    w, h = a.size
    total = 0
    changed = 0
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            ra, ga, ba = pa[x, y]
            rb, gb, bb = pb[x, y]
            d = abs(ra - rb) + abs(ga - gb) + abs(ba - bb)
            total += d
            if d > 40:
                changed += 1
                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
    mean = total / (w * h)
    bbox = (minx, miny, maxx, maxy) if maxx >= 0 else None
    return mean, changed, bbox


SRC = "sample_video.mp4"
print("== A. 平铺水印：成品帧 与 原片帧 对比 ==")
for name, exp_changed in [("out_tiled_text.mp4", 5000), ("out_tiled_image.mp4", 5000)]:
    src = grab(SRC, 1.0)
    out = grab(name, 1.0)
    mean, changed, bbox = diff_stats(src, out)
    check(f"{name} 存在明显水印差异", changed >= exp_changed,
          f"差异像素={changed} 均值差={mean:.1f} bbox={bbox}")

def diff_map(a: Image.Image, b: Image.Image, thresh: int = 40):
    """返回 (差异像素列表 (x,y), 数量)。"""
    pa, pb = a.load(), b.load()
    w, h = a.size
    pts = []
    for y in range(h):
        for x in range(w):
            ra, ga, ba = pa[x, y]
            rb, gb, bb = pb[x, y]
            if abs(ra - rb) + abs(ga - gb) + abs(ba - bb) > thresh:
                pts.append((x, y))
    return pts


def centroid(pts):
    if not pts:
        return None
    return sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)


print("== B. 移动水印：与期望轨迹位置对比 ==")
from app.models import WatermarkConfig, KIND_TEXT, KIND_IMAGE, MODE_MOTION, \
    TRAJECTORY_CIRCLE, TRAJECTORY_FIGURE8
from app.core.motion import position_at
from app.core.watermark import render_cell

CASE_MOTION = [
    ("out_motion_text.mp4", WatermarkConfig(
        kind=KIND_TEXT, mode=MODE_MOTION, text="© 2025",
        text_opacity=220, stroke_width=2, stroke_color=(0, 0, 0),
        trajectory=TRAJECTORY_CIRCLE, speed=1.2,
        motion_scale=0.18, motion_opacity=200)),
    ("out_motion_image.mp4", WatermarkConfig(
        kind=KIND_IMAGE, image_path=str(OUT / "logo.png"), mode=MODE_MOTION,
        motion_scale=0.12, motion_opacity=200, img_radius=30,
        trajectory=TRAJECTORY_FIGURE8, speed=1.0)),
]
for name, cfg in CASE_MOTION:
    ok = True
    detail = []
    for t in (2.0, 3.0):
        src = grab(SRC, t)
        out = grab(name, t)
        pts = diff_map(src, out, thresh=120)
        c = centroid(pts)
        cell = render_cell(cfg, out.width, out.height)
        ex, ey = position_at(cfg, t, out.width, out.height, cell.width, cell.height)
        # 期望中心
        ecx, ecy = ex + cell.width / 2, ey + cell.height / 2
        if c is None:
            ok = False
            detail.append(f"t={t}s 无差异像素")
            continue
        dist = ((c[0] - ecx) ** 2 + (c[1] - ecy) ** 2) ** 0.5
        hit = dist < 50
        ok = ok and hit
        detail.append(f"t={t}s 质心{tuple(round(v,1) for v in c)} 期望中心{round(ecx,1)},{round(ecy,1)} 距离{dist:.1f}")
    check(f"{name} 水印位于期望轨迹位置", ok, " | ".join(detail))

print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
sys.exit(1 if failures else 0)
