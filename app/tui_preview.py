"""TUI 预览渲染：PIL 图像 → 终端半块像素字符（▀ + 24bit 颜色）。

原理：把图像缩放到 (cols, rows*2)，每两个竖向像素合并为一个 "▀" 字符——
上像素作为字符前景色、下像素作为背景色，一屏即可显示两倍纵向分辨率。
输出为 rich.text.Text（带 RGB style span），Textual Static 直接渲染。

视频帧抽取复用 imageio-ffmpeg（按精确帧索引读，与像素验证一致的怪癖——
不用 -ss 抽帧避免错位）；水印合成复用 app/core/preview.py。
"""
from __future__ import annotations

from pathlib import Path

import imageio_ffmpeg
from PIL import Image
from rich.text import Text

HALF = "▀"  # U+2580 上半块


def image_to_half_blocks(img: Image.Image, max_cols: int = 78,
                         max_rows: int = 40) -> Text:
    """PIL 图像 → 半块字符 Text（宽度自适应 max_cols，高度自适应 max_rows）。"""
    img = img.convert("RGB")
    cols = min(max_cols, img.width) or 1
    rows2 = min(max_rows * 2, img.height * cols // max(img.width, 1) * 2) or 2
    # 等比缩放到 (cols, rows2)，rows2 必须为偶数
    ratio = min(cols / img.width, rows2 / img.height)
    small = img.resize((max(1, round(img.width * ratio)),
                        max(2, round(img.height * ratio))), Image.LANCZOS)
    if small.height % 2:
        small = small.crop((0, 0, small.width, small.height - 1))
    small.load()

    text = Text()
    px = small.load()
    for y in range(0, small.height - 1, 2):
        for x in range(small.width):
            top = px[x, y]
            bottom = px[x, y + 1]
            text.append(HALF, style=f"rgb({top[0]},{top[1]},{top[2]}) "
                                    f"on rgb({bottom[0]},{bottom[1]},{bottom[2]})")
        if y + 2 < small.height:
            text.append("\n")
    return text


def grab_composited_frame(video: str, cfg, t: float) -> Image.Image:
    """抽取视频 t 秒处的帧并合成水印（复用 app.core.preview）。"""
    from .core import preview as _preview
    return _preview.render_preview_frame(video, cfg, t)


def sketch(cfg, frame_w: int = 640, frame_h: int = 360) -> Image.Image:
    """轨迹示意图（复用 app.core.preview）。"""
    from .core import preview as _preview
    return _preview.sketch_trajectory(cfg, frame_w, frame_h)


def video_duration(video: str) -> float:
    """视频时长（秒），probe 失败返回 0。"""
    try:
        gen = imageio_ffmpeg.read_frames(str(video))
        meta = next(gen)
        return float(meta.get("duration", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0.0
