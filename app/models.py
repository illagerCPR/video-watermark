"""视频水印软件 - 水印配置数据模型

所有参数集中定义在此，GUI / CLI / 引擎共用。
支持序列化为 JSON（保存/加载配置）。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Optional

# 模式：平铺（全屏铺满） / 移动（轨迹运动）
MODE_TILED = "tiled"
MODE_MOTION = "motion"
MODES = (MODE_TILED, MODE_MOTION)

# 水印来源
KIND_TEXT = "text"
KIND_IMAGE = "image"
KINDS = (KIND_TEXT, KIND_IMAGE)

# 预设移动轨迹（6 种，>= 需求要求的 5 种）
TRAJECTORY_HORIZONTAL = "horizontal"  # 水平往返
TRAJECTORY_VERTICAL = "vertical"      # 垂直往返
TRAJECTORY_DIAGONAL = "diagonal"      # 对角线往返
TRAJECTORY_CIRCLE = "circle"          # 圆周运动
TRAJECTORY_FIGURE8 = "figure8"        # 8 字形（李萨如曲线）
TRAJECTORY_SINE = "sine"              # 正弦波漂移
TRAJECTORIES = (
    TRAJECTORY_HORIZONTAL,
    TRAJECTORY_VERTICAL,
    TRAJECTORY_DIAGONAL,
    TRAJECTORY_CIRCLE,
    TRAJECTORY_FIGURE8,
    TRAJECTORY_SINE,
)

# 轨迹中文名（GUI 下拉用）
TRAJECTORY_LABELS = {
    TRAJECTORY_HORIZONTAL: "水平往返",
    TRAJECTORY_VERTICAL: "垂直往返",
    TRAJECTORY_DIAGONAL: "对角线往返",
    TRAJECTORY_CIRCLE: "圆周运动",
    TRAJECTORY_FIGURE8: "8 字形",
    TRAJECTORY_SINE: "正弦波漂移",
}


@dataclass
class WatermarkConfig:
    """水印全部可调参数"""

    # ---------- 来源 ----------
    kind: str = KIND_TEXT            # text / image
    text: str = "CONFIDENTIAL"       # 文字水印内容，支持 \n 多行
    image_path: str = ""             # 图片水印路径

    # ---------- 文字样式 ----------
    font_name: str = ""              # 字体（空 = 自动选系统中文字体）
    font_size: int = 48              # 字号（像素）
    text_color: tuple = (255, 255, 255)  # 文字 RGB 颜色
    text_opacity: int = 90           # 文字透明度 0~255
    stroke_width: int = 0            # 描边宽度（0 = 无）
    stroke_color: tuple = (0, 0, 0)  # 描边颜色

    # ---------- 图片样式 ----------
    img_scale: float = 0.3           # 图片水印宽度 = 帧宽 * 此比例（平铺模式）
    img_opacity: int = 128           # 图片透明度 0~255
    img_radius: int = 0              # 图片圆角（像素，0 = 直角）

    # ---------- 模式 ----------
    mode: str = MODE_TILED           # tiled / motion

    # ---------- 平铺参数 ----------
    angle: float = 30.0              # 整幅瓦片旋转角度 -180~180（度）
    tile_dx: int = 260               # 平铺横向间距（像素）
    tile_dy: int = 160               # 平铺纵向间距（像素）
    offset_x: int = 0                # 平铺整体偏移 X
    offset_y: int = 0                # 平铺整体偏移 Y

    # ---------- 移动参数 ----------
    trajectory: str = TRAJECTORY_HORIZONTAL  # 轨迹名
    speed: float = 1.0               # 移动速度倍率
    motion_scale: float = 0.2        # 移动水印宽度 = 帧宽 * 此比例
    motion_opacity: int = 200        # 移动水印透明度 0~255
    motion_rotate: bool = False      # 移动水印是否随时间自转（每周期转一圈）

    # ---------- 出现时间范围（秒） ----------
    start_sec: float = 0.0           # 开始时间，0 = 从开头
    end_sec: Optional[float] = None  # 结束时间，None = 直到结尾


# ---------------------------------------------------------------------------
# JSON 序列化（保存/加载配置）
# ---------------------------------------------------------------------------

def _default_json(obj):
    if isinstance(obj, tuple):
        return list(obj)
    return str(obj)


def config_to_json(cfg: WatermarkConfig) -> str:
    """序列化为 JSON 字符串（用于保存配置）。"""
    d = asdict(cfg)
    return json.dumps(d, ensure_ascii=False, indent=2, default=_default_json)


def json_to_config(text: str) -> WatermarkConfig:
    """从 JSON 字符串恢复配置；未知字段忽略，缺失字段用默认值。"""
    raw = json.loads(text)
    valid = {f.name: f for f in fields(WatermarkConfig)}
    kwargs = {}
    for key, value in raw.items():
        if key not in valid:
            continue
        f = valid[key]
        if f.type is bool and isinstance(value, str):
            value = value.lower() in ("1", "true", "yes", "on")
        if f.name in ("text_color", "stroke_color") and isinstance(value, list):
            value = tuple(value)
        if f.name in ("font_size", "tile_dx", "tile_dy", "offset_x", "offset_y",
                      "stroke_width", "img_radius", "text_opacity", "img_opacity",
                      "motion_opacity"):
            value = int(value)
        if f.name in ("font_size", "tile_dx", "tile_dy"):
            value = max(1, int(value))
        kwargs[key] = value
    return WatermarkConfig(**kwargs)


__all__ = [
    "WatermarkConfig",
    "MODE_TILED", "MODE_MOTION", "MODES",
    "KIND_TEXT", "KIND_IMAGE", "KINDS",
    "TRAJECTORIES", "TRAJECTORY_LABELS",
    "config_to_json", "json_to_config",
]
