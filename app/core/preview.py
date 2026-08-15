"""预览支持：单帧水印效果渲染 + 移动轨迹示意图。

GUI 与 CLI（--preview 未来可选）共用。
"""
from __future__ import annotations

import imageio_ffmpeg
from PIL import Image, ImageDraw

from ..models import MODE_MOTION, WatermarkConfig
from .compositor import WatermarkCompositor
from .encoder import probe
from .motion import BASE_CYCLE_SECONDS, position_at
from .watermark import render_cell


def render_preview_frame(input_path: str, cfg: WatermarkConfig,
                         t_sec: float = 0.0, max_width: int = 960) -> Image.Image:
    """渲染输入视频在 t_sec 秒处叠加水印后的帧（用于 GUI 预览）。"""
    meta = probe(input_path)
    W, H, fps = meta["width"], meta["height"], meta["fps"]

    gen = imageio_ffmpeg.read_frames(input_path, pix_fmt="rgb24")
    meta2 = next(gen)  # 元数据 dict
    idx = int(round(t_sec * fps))
    frame = None
    for i, fb in enumerate(gen):
        if i == idx:
            frame = Image.frombytes("RGB", (W, H), fb)
            break
    gen.close()
    if frame is None:
        raise RuntimeError(f"帧 {idx} 超出视频范围（共约 {meta['frames']} 帧）")

    comp = WatermarkCompositor(cfg, W, H, fps)
    comp.apply(frame, t_sec)

    if max_width and frame.width > max_width:
        frame = frame.resize((max_width, int(frame.height * max_width / frame.width)),
                             Image.LANCZOS)
    return frame


def sketch_trajectory(cfg: WatermarkConfig, frame_w: int, frame_h: int,
                      steps: int = 240) -> Image.Image:
    """绘制移动水印一个完整周期的轨迹示意图（白底 RGB 图）。

    若 cfg.mode 不是移动模式，返回一张提示图。
    """
    if cfg.mode != MODE_MOTION:
        img = Image.new("RGB", (frame_w, frame_h), (250, 250, 250))
        d = ImageDraw.Draw(img)
        d.text((frame_w // 2 - 60, frame_h // 2), "请在移动模式下查看轨迹",
               fill=(120, 120, 120))
        return img

    cell = render_cell(cfg, frame_w, frame_h)
    img = Image.new("RGB", (frame_w, frame_h), (250, 250, 250))
    d = ImageDraw.Draw(img)

    pts = []
    for i in range(steps + 1):
        t = BASE_CYCLE_SECONDS * i / steps
        x, y = position_at(cfg, t, frame_w, frame_h, cell.width, cell.height)
        pts.append((x, y))

    # 轨迹线
    d.line(pts, fill=(232, 92, 92), width=3, joint="curve")
    # 起点 / 终点标记
    for i, (mx, my) in ((0, pts[0]), (-1, pts[-1])):
        d.ellipse([mx - 5, my - 5, mx + 5, my + 5],
                  fill=(232, 92, 92) if i == 0 else (64, 128, 255))
    # 水印当前位置示意（半透明矩形 + 说明）
    x0, y0 = pts[0]
    d.rectangle([x0, y0, x0 + cell.width, y0 + cell.height],
                outline=(64, 128, 255), width=2)
    d.text((8, 8), "红色线 = 移动轨迹   蓝框 = 水印起始位置",
           fill=(80, 80, 80))
    return img


__all__ = ["render_preview_frame", "sketch_trajectory"]
