"""步骤 4 验收样例生成：演示角度控制与时间范围。

产出（outputs/）：
  accept_tiled45.mp4          平铺·45°·多行文字（角度控制）
  accept_motion_range.mp4     移动·正弦波·仅 1.0~3.5s 出现（时间范围）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models import (  # noqa: E402
    KIND_TEXT, MODE_MOTION, MODE_TILED, TRAJECTORY_SINE, WatermarkConfig,
)
from app.core.encoder import generate_sample_video, process  # noqa: E402

OUT = ROOT / "outputs"
SRC = OUT / "sample_video.mp4"

if not SRC.exists():
    generate_sample_video(str(SRC), size=(640, 360), duration=5.0, fps=30)

print("生成验收样例 1：平铺·45°·多行文字")
process(str(SRC), str(OUT / "accept_tiled45.mp4"), WatermarkConfig(
    kind=KIND_TEXT, mode=MODE_TILED,
    text="内部资料\n严禁外传",
    font_size=44, text_opacity=80, stroke_width=1,
    angle=45.0, tile_dx=340, tile_dy=220,
), crf=23, preset="medium")

print("生成验收样例 2：移动·正弦波·时间范围 1.0~3.5s")
process(str(SRC), str(OUT / "accept_motion_range.mp4"), WatermarkConfig(
    kind=KIND_TEXT, mode=MODE_MOTION,
    text="© 2025 演示", font_size=44,
    text_opacity=230, stroke_width=2,
    trajectory=TRAJECTORY_SINE, speed=1.0,
    motion_scale=0.22, motion_opacity=220,
    start_sec=1.0, end_sec=3.5,
), crf=23, preset="medium")

print("完成。")
