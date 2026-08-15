"""核心渲染：文字 / 图片水印的生成与全屏平铺瓦片。

设计要点：
- 水印单元格（文字或图片）先渲染为一张透明 RGBA 图；
- 平铺模式：把单元格按角度旋转后，按行列间距平铺成一张与帧等大的
  透明瓦片，之后每一帧只需一次 alpha 合成，性能最优；
- 移动模式：只渲染单张单元格，按轨迹逐帧定位合成。
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

from ..models import KIND_IMAGE, MODE_MOTION, MODE_TILED, WatermarkConfig

# ---------------------------------------------------------------------------
# 字体解析
# ---------------------------------------------------------------------------

# 常用中文字体：显示名（家族名） -> 字体文件名
FONT_ALIASES = {
    "微软雅黑": "msyh.ttc",
    "microsoft yahei": "msyh.ttc",
    "yahei": "msyh.ttc",
    "黑体": "simhei.ttf",
    "simhei": "simhei.ttf",
    "宋体": "simsun.ttc",
    "simsun": "simsun.ttc",
    "楷体": "simkai.ttf",
    "kaiti": "simkai.ttf",
    "等线": "Deng.ttf",
    "dengxian": "Deng.ttf",
    "隶书": "SIMLI.TTF",
    "arial": "arial.ttf",
    "times new roman": "times.ttf",
    "courier new": "cour.ttf",
}

# Windows 常见中文字体候选（按优先级）
_CJK_CANDIDATES = [
    "msyh.ttc",      # 微软雅黑
    "msyhbd.ttc",    # 微软雅黑 Bold
    "simhei.ttf",    # 黑体
    "simsun.ttc",    # 宋体
    "Deng.ttf",      # 等线
    "simkai.ttf",    # 楷体
]


def _font_dirs() -> list[str]:
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR") or r"C:\Windows"
        return [os.path.join(windir, "Fonts")]
    return [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
    ]


def _search_font_file(filename: str) -> str | None:
    for d in _font_dirs():
        p = os.path.join(d, filename)
        if os.path.isfile(p):
            return p
    return None


def _default_font_name() -> str:
    """自动选择一个支持中文的默认字体名（若无则返回 ''）。"""
    for name in _CJK_CANDIDATES:
        if _search_font_file(name):
            # 返回显示名，方便 GUI 显示
            return {"msyh.ttc": "微软雅黑"}.get(name, name)
    return ""


def resolve_font_path(font_name: str) -> str | None:
    """把用户给的字体名（路径 / 家族名 / 文件名）解析为可加载的字体文件路径。

    返回 None 表示找不到，调用方回退到默认字体。
    """
    if not font_name:
        return None
    if os.path.isfile(font_name):
        return font_name
    # 家族名 / 文件名 -> 搜索系统字体目录
    candidates = []
    alias_file = FONT_ALIASES.get(font_name.lower())
    if alias_file:
        candidates.append(alias_file)
    candidates.append(font_name)
    # 文件名可能带后缀或不带
    if "." not in font_name:
        candidates += [font_name + ".ttf", font_name + ".ttc", font_name + ".otf"]
    for c in candidates:
        hit = _search_font_file(c)
        if hit:
            return hit
    return None


def list_available_fonts() -> list[str]:
    """返回系统可用字体显示名列表（供 GUI 下拉选择）。"""
    names = list(FONT_ALIASES.keys())
    seen = set(n.lower() for n in names)
    for d in _font_dirs():
        if not os.path.isdir(d):
            continue
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for e in sorted(entries):
            if not e.lower().endswith((".ttf", ".ttc", ".otf")):
                continue
            if e.lower() in seen:
                continue
            seen.add(e.lower())
            names.append(e)
    return names


def load_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    """加载字体；找不到时回退到系统中文字体，再回退到 Pillow 默认字体。"""
    path = resolve_font_path(font_name)
    if not path:
        default_name = _default_font_name()
        if default_name:
            path = resolve_font_path(default_name)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ValueError):
            pass
    return ImageFont.load_default(size)


# ---------------------------------------------------------------------------
# 文本换行
# ---------------------------------------------------------------------------

def _measure_text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def wrap_text(text: str, font, max_width: int) -> list[str]:
    """按最大宽度自动换行；显式换行符 \n 优先。返回行列表。"""
    lines: list[str] = []
    img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(img)
    for raw in text.split("\n"):
        if not raw:
            lines.append("")
            continue
        if max_width <= 0:
            lines.append(raw)
            continue
        current = ""
        for ch in raw:
            probe = current + ch
            if _measure_text_width(draw, probe, font) <= max_width:
                current = probe
            else:
                if current:
                    lines.append(current)
                current = ch
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# 单元格渲染
# ---------------------------------------------------------------------------

def render_text_cell(cfg: WatermarkConfig, target_width: int = 0,
                     force_size: int = 0) -> Image.Image:
    """渲染多行文字为透明 RGBA 图。

    target_width > 0 时按目标宽度缩放（移动模式按比例控制大小）；
    force_size > 0 时忽略 cfg.font_size 用指定字号。
    """
    size = force_size if force_size > 0 else cfg.font_size
    font = load_font(cfg.font_name, size)

    # 先按自然尺寸渲染
    probe = Image.new("RGBA", (8, 8))
    draw = ImageDraw.Draw(probe)
    lines = wrap_text(cfg.text or " ", font, max_width=0)
    line_h = size * 1.25
    widths = [_measure_text_width(draw, ln, font) for ln in lines]
    text_w = max(widths) if widths else 0
    pad = max(4, size // 4)
    canvas_w = text_w + pad * 2
    canvas_h = max(1, int(line_h * len(lines)) + pad * 2)

    cell = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(cell)
    y = pad
    for ln in lines:
        w = _measure_text_width(d, ln, font)
        x = (canvas_w - w) // 2
        if cfg.stroke_width > 0:
            d.text((x, y), ln, font=font, fill=cfg.text_color + (cfg.text_opacity,),
                   stroke_width=cfg.stroke_width, stroke_fill=cfg.stroke_color)
        else:
            d.text((x, y), ln, font=font, fill=cfg.text_color + (cfg.text_opacity,))
        y += line_h

    # 缩放
    if target_width > 0 and cell.width > 0 and cell.width != target_width:
        ratio = target_width / cell.width
        new_h = max(1, int(cell.height * ratio))
        cell = cell.resize((target_width, new_h), Image.LANCZOS)
    return cell


def _apply_round_corners(img: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return img
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=radius, fill=255)
    out = img.copy()
    out.putalpha(mask)
    return out


def render_image_cell(cfg: WatermarkConfig, target_width: int = 0) -> Image.Image:
    """加载图片并返回透明 RGBA 单元格。

    target_width > 0 时按目标宽度缩放；否则按 cfg.img_scale 占帧宽比例（由调用方
    在拿到帧宽后换算传入）。圆角 / 透明度在此应用。
    """
    if not cfg.image_path or not os.path.isfile(cfg.image_path):
        raise FileNotFoundError(f"图片水印不存在：{cfg.image_path}")
    img = Image.open(cfg.image_path).convert("RGBA")
    if target_width > 0 and img.width > 0:
        ratio = target_width / img.width
        new_h = max(1, int(img.height * ratio))
        img = img.resize((target_width, new_h), Image.LANCZOS)
    img = _apply_round_corners(img, cfg.img_radius)
    # 应用整体透明度
    if cfg.img_opacity < 255:
        alpha = img.getchannel("A").point(lambda a: a * cfg.img_opacity // 255)
        img.putalpha(alpha)
    return img


def render_cell(cfg: WatermarkConfig, frame_w: int, frame_h: int) -> Image.Image:
    """按当前配置渲染单个水印单元格（未旋转），并换算好目标宽度。

    - 平铺-文字：按 cfg.font_size 自然尺寸
    - 平铺-图片：宽度 = frame_w * cfg.img_scale
    - 移动模式（文字/图片）：宽度 = frame_w * cfg.motion_scale
    """
    if cfg.mode == MODE_MOTION:
        target = max(8, int(frame_w * cfg.motion_scale))
        if cfg.kind == KIND_IMAGE:
            cell = render_image_cell(cfg, target)
        else:
            cell = render_text_cell(cfg, target_width=target,
                                    force_size=max(12, int(target * 0.9)))
    else:  # MODE_TILED
        if cfg.kind == KIND_IMAGE:
            target = max(8, int(frame_w * cfg.img_scale))
            cell = render_image_cell(cfg, target)
        else:
            cell = render_text_cell(cfg, target_width=0)
    return cell


# ---------------------------------------------------------------------------
# 平铺瓦片
# ---------------------------------------------------------------------------

def rotate_cell(cell: Image.Image, angle: float) -> Image.Image:
    """旋转单元格（角度为 0 时原样返回）。"""
    if not angle:
        return cell
    return cell.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))


def make_tile(cfg: WatermarkConfig, frame_w: int, frame_h: int) -> Image.Image:
    """生成覆盖整帧的透明平铺瓦片（RGBA，帧等大）。

    流程：渲染单元格 -> 旋转 -> 按间距行列平铺。
    """
    cell = render_cell(cfg, frame_w, frame_h)
    cell = rotate_cell(cell, cfg.angle)

    step_x = max(cfg.tile_dx, cell.width + 8)
    step_y = max(cfg.tile_dy, cell.height + 8)

    tile = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
    # 覆盖范围：从负方向多铺一格，保证边缘铺满
    i0 = -1 - cfg.offset_x // step_x if cfg.offset_x else -1
    i1 = frame_w // step_x + 1
    j0 = -1 - cfg.offset_y // step_y if cfg.offset_y else -1
    j1 = frame_h // step_y + 1
    for j in range(j0, j1 + 1):
        y = cfg.offset_y + j * step_y
        for i in range(i0, i1 + 1):
            x = cfg.offset_x + i * step_x
            tile.alpha_composite(cell, (int(x), int(y)))
    return tile
