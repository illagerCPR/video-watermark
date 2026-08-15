"""命令行入口（引擎能力脚本化，GUI 之外的另一使用方式）。

用法示例：
  python -m app.cli --input in.mp4 --output out.mp4 \
      --mode tiled --text "机密文件\\n请勿外传" --angle 30
  python -m app.cli --input in.mp4 --output out.mp4 \
      --mode motion --trajectory circle --speed 1.5 --set motion_opacity=180

  --config cfg.json  读取完整配置（JSON，由 config_to_json 生成）
  --set k=v          覆盖任意配置字段（可重复）
  --crf 23 --preset medium --scale 1.0
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

from .models import WatermarkConfig, config_to_json, json_to_config
from .core.encoder import process, probe


def _coerce(name: str, value: str):
    """按字段类型把字符串参数转成对应 Python 值。"""
    for f in fields(WatermarkConfig):
        if f.name == name:
            t = str(f.type)
            if f.name in ("text_color", "stroke_color"):
                try:
                    parts = [int(x.strip()) for x in value.split(",")]
                    return tuple(parts)
                except ValueError:
                    raise SystemExit(f"--set {name}: 颜色需形如 255,255,255")
            if "bool" in t:
                return value.lower() in ("1", "true", "yes", "on")
            if "float" in t:
                return float(value)
            if "int" in t:
                return int(value)
            return value
    raise SystemExit(f"未知配置字段：{name}")


def build_config(args) -> WatermarkConfig:
    cfg = WatermarkConfig()
    if args.config:
        cfg = json_to_config(Path(args.config).read_text(encoding="utf-8"))
    if args.mode:
        cfg.mode = args.mode
    if args.kind:
        cfg.kind = args.kind
    if args.text is not None:
        cfg.text = args.text
    if args.trajectory:
        cfg.trajectory = args.trajectory
    if args.angle is not None:
        cfg.angle = args.angle
    if args.image:
        cfg.image_path = args.image
        cfg.kind = "image"
    for kv in args.set or []:
        if "=" not in kv:
            raise SystemExit(f"--set 需形如 k=v：{kv}")
        k, v = kv.split("=", 1)
        setattr(cfg, k, _coerce(k, v))
    return cfg


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="video-watermark", description="视频水印工具（命令行）")
    p.add_argument("--input", required=True, help="输入视频")
    p.add_argument("--output", required=True, help="输出视频")
    p.add_argument("--config", help="JSON 配置（可选）")
    p.add_argument("--mode", choices=["tiled", "motion"], help="平铺 / 移动")
    p.add_argument("--kind", choices=["text", "image"], help="文字 / 图片水印")
    p.add_argument("--text", help="文字内容（\\n 换行）")
    p.add_argument("--image", help="图片水印路径")
    p.add_argument("--angle", type=float, help="平铺旋转角度")
    p.add_argument("--trajectory", help="移动轨迹")
    p.add_argument("--set", action="append", help="覆盖字段：--set k=v")
    p.add_argument("--crf", type=int, default=23)
    p.add_argument("--preset", default="medium")
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--print-config", action="store_true", help="打印最终配置后退出")
    args = p.parse_args(argv)

    cfg = build_config(args)
    if args.print_config:
        print(config_to_json(cfg))
        return 0

    meta = probe(args.input)
    print(f"输入: {args.input}  {meta['width']}x{meta['height']}  "
          f"{meta['fps']:.2f}fps  ~{meta['duration_sec']:.1f}s  ({meta['frames']}帧)")

    def progress(done, total):
        if total:
            pct = done * 100 // total
            print(f"\r  进度 {pct:3d}%  ({done}/{total})", end="", flush=True)

    print("开始处理...")
    stats = process(args.input, args.output, cfg,
                    progress_cb=progress, crf=args.crf,
                    preset=args.preset, scale=args.scale)
    print(f"\n完成: {args.output}  {stats['width']}x{stats['height']}  "
          f"{stats['frames']} 帧")
    return 0


if __name__ == "__main__":
    sys.exit(main())
