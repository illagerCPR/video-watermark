"""移动水印轨迹计算。

6 种预设轨迹（满足需求 >=5）：
1. horizontal  水平往返
2. vertical    垂直往返
3. diagonal    对角线往返
4. circle      圆周运动
5. figure8     8 字形（李萨如曲线 x=sin(2a), y=sin(a)）
6. sine        正弦波漂移（水平往返 + 纵向正弦起伏）

所有轨迹输出水印左上角坐标（含边界留白），保证水印完整出现在画面内。
"""
from __future__ import annotations

import math

from ..models import (
    TRAJECTORY_CIRCLE,
    TRAJECTORY_DIAGONAL,
    TRAJECTORY_FIGURE8,
    TRAJECTORY_HORIZONTAL,
    TRAJECTORY_SINE,
    TRAJECTORY_VERTICAL,
    WatermarkConfig,
)

# 一个完整轨迹周期的基础时长（秒），speed 倍率放大/缩小
BASE_CYCLE_SECONDS = 8.0


def _tri(phase: float) -> float:
    """三角波：phase∈[0,1) -> [0,1]，起点 0、中点 1、回到 0。"""
    p = phase % 1.0
    return 1.0 - abs(2.0 * p - 1.0)


def _phase(cfg: WatermarkConfig, t: float) -> float:
    return (t * cfg.speed / BASE_CYCLE_SECONDS) % 1.0


def position_at(cfg: WatermarkConfig, t: float,
                frame_w: int, frame_h: int,
                wm_w: int, wm_h: int) -> tuple[float, float]:
    """返回 t 时刻水印左上角坐标 (x, y)。"""
    margin = 8
    x_lo = margin
    x_hi = max(margin + 1, frame_w - wm_w - margin)
    y_lo = margin
    y_hi = max(margin + 1, frame_h - wm_h - margin)
    cx = (x_lo + x_hi) / 2.0
    cy = (y_lo + y_hi) / 2.0
    rx = (x_hi - x_lo) / 2.0
    ry = (y_hi - y_lo) / 2.0

    phase = _phase(cfg, t)
    a = 2.0 * math.pi * phase
    tr = cfg.trajectory

    if tr == TRAJECTORY_HORIZONTAL:
        x = x_lo + (x_hi - x_lo) * _tri(phase)
        y = cy
    elif tr == TRAJECTORY_VERTICAL:
        x = cx
        y = y_lo + (y_hi - y_lo) * _tri(phase)
    elif tr == TRAJECTORY_DIAGONAL:
        k = _tri(phase)
        x = x_lo + (x_hi - x_lo) * k
        y = y_lo + (y_hi - y_lo) * k
    elif tr == TRAJECTORY_CIRCLE:
        r = min(rx, ry)
        x = cx + r * math.cos(a)
        y = cy + r * math.sin(a)
    elif tr == TRAJECTORY_FIGURE8:
        # 李萨如：x 一个周期跑两圈、y 一圈 -> 8 字形（竖向 8）
        r = min(rx, ry * 1.4)
        x = cx + r * math.sin(2.0 * a)
        y = cy + r * 0.6 * math.sin(a)
    elif tr == TRAJECTORY_SINE:
        x = x_lo + (x_hi - x_lo) * _tri(phase)
        y = cy + ry * 0.9 * math.sin(2.0 * math.pi * 2.0 * phase)
    else:  # 未知轨迹回退为水平往返
        x = x_lo + (x_hi - x_lo) * _tri(phase)
        y = cy

    return x, y


def motion_angle(cfg: WatermarkConfig, t: float) -> float:
    """移动水印随时间自转角度（每周期转一圈）。cfg.motion_rotate 为 False 时返回 0。"""
    if not cfg.motion_rotate:
        return 0.0
    return 360.0 * _phase(cfg, t)


__all__ = ["position_at", "motion_angle", "BASE_CYCLE_SECONDS"]
