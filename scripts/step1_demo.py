"""步骤 1 验证脚本：跑通核心引擎并产出样例输出。

执行： .venv\\Scripts\\python.exe scripts\\step1_demo.py
产出（均在 outputs/ 目录）：
  sample_video.mp4   测试样片（testsrc2 动态彩色）
  logo.png           测试 logo
  out_tiled_text.mp4     平铺·多行文字水印（角度 30°）
  out_tiled_image.mp4    平铺·图片水印（圆角）
  out_motion_text.mp4    移动·文字水印（圆周轨迹）
  out_motion_image.mp4   移动·图片水印（8 字形轨迹）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models import (  # noqa: E402
    WatermarkConfig, KIND_TEXT, KIND_IMAGE,
    MODE_TILED, MODE_MOTION,
    TRAJECTORY_CIRCLE, TRAJECTORY_FIGURE8,
)
from app.core.encoder import (  # noqa: E402
    generate_sample_logo, generate_sample_video, process,
)


def run(name, cfg, **kw):
    print(f"  ▶ {name}")
    stats = process(SAMPLE_VIDEO, OUT_DIR / f"{name}.mp4", cfg, **kw)
    print(f"    ✓ {name}.mp4  {stats['width']}x{stats['height']}  {stats['frames']} 帧")


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)

    print("[1/2] 生成测试素材...")
    generate_sample_video(str(SAMPLE_VIDEO), size=(640, 360), duration=5.0, fps=30)
    generate_sample_logo(str(LOGO), text="LOGO", size=220)
    print("  ✓ sample_video.mp4 与 logo.png 已生成")

    print("[2/2] 生成 4 种水印输出...")

    # 1) 平铺·多行文字（角度 30°，半透明）
    run("out_tiled_text", WatermarkConfig(
        kind=KIND_TEXT, mode=MODE_TILED,
        text="机密文件\n请勿外传",
        font_size=42, text_opacity=70,
        angle=30.0, tile_dx=320, tile_dy=200,
    ))

    # 2) 平铺·图片（缩放 + 圆角 + 透明度）
    run("out_tiled_image", WatermarkConfig(
        kind=KIND_IMAGE, image_path=str(LOGO), mode=MODE_TILED,
        img_scale=0.18, img_opacity=110, img_radius=28,
        angle=15.0, tile_dx=300, tile_dy=300,
    ))

    # 3) 移动·文字（圆周轨迹，速度 1.2；带黑色描边保证亮/暗背景都可见）
    run("out_motion_text", WatermarkConfig(
        kind=KIND_TEXT, mode=MODE_MOTION,
        text="© 2025", font_size=48,
        text_opacity=220, stroke_width=2, stroke_color=(0, 0, 0),
        trajectory=TRAJECTORY_CIRCLE, speed=1.2,
        motion_scale=0.18, motion_opacity=200,
    ))

    # 4) 移动·图片（8 字形轨迹 + 自转）
    run("out_motion_image", WatermarkConfig(
        kind=KIND_IMAGE, image_path=str(LOGO), mode=MODE_MOTION,
        img_scale=0.2, motion_scale=0.12, motion_opacity=200, img_radius=30,
        trajectory=TRAJECTORY_FIGURE8, speed=1.0, motion_rotate=True,
    ))

    print("\n全部完成！输出目录：", OUT_DIR)
    return 0


if __name__ == "__main__":
    OUT_DIR = ROOT / "outputs"
    SAMPLE_VIDEO = OUT_DIR / "sample_video.mp4"
    LOGO = OUT_DIR / "logo.png"
    raise SystemExit(main())
