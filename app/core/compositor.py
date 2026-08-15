"""逐帧合成：把水印叠加到视频帧上。

- 平铺模式：整帧瓦片一次 alpha 合成
- 移动模式：单张单元格按坐标合成
- 均通过 PIL 的 paste(mask=自身) 完成，RGB 底图即可，速度快
"""
from __future__ import annotations

from PIL import Image

from ..models import MODE_MOTION, MODE_TILED, WatermarkConfig
from .motion import motion_angle, position_at
from .watermark import make_tile, render_cell, rotate_cell


def in_time_range(cfg: WatermarkConfig, t: float) -> bool:
    """判断时刻 t（秒）是否在水印出现时间范围内。"""
    if t < cfg.start_sec - 1e-6:
        return False
    if cfg.end_sec is not None and t > cfg.end_sec + 1e-6:
        return False
    return True


class WatermarkCompositor:
    """一次视频处理全程复用的合成器：平铺瓦片 / 移动水印只渲染一次。"""

    def __init__(self, cfg: WatermarkConfig, frame_w: int, frame_h: int, fps: float):
        self.cfg = cfg
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.fps = fps
        if cfg.mode == MODE_TILED:
            self.tile = make_tile(cfg, frame_w, frame_h)
        else:
            self.cell = render_cell(cfg, frame_w, frame_h)
            self.cell = rotate_cell(self.cell, 0.0)

    def apply(self, frame_rgb: Image.Image, t: float) -> Image.Image:
        """把水印叠加到帧上（原地修改并返回）。t 为当前帧时间（秒）。"""
        if not in_time_range(self.cfg, t):
            return frame_rgb
        if self.cfg.mode == MODE_MOTION:
            x, y = position_at(self.cfg, t, self.frame_w, self.frame_h,
                               self.cell.width, self.cell.height)
            cell = self.cell
            if self.cfg.motion_rotate:
                ang = motion_angle(self.cfg, t)
                if ang:
                    cell = rotate_cell(self.cell, ang)
                    x, y = position_at(self.cfg, t, self.frame_w, self.frame_h,
                                       cell.width, cell.height)
            frame_rgb.paste(cell, (int(x), int(y)), cell)
        else:
            frame_rgb.paste(self.tile, (0, 0), self.tile)
        return frame_rgb
