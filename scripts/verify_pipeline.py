"""流水线专项测试：并行帧流水线（读/合成/写三阶段）的正确性。

覆盖：
  1. 串行(parallel=1) 与 并行(parallel=4) 输出字节级一致（MD5 相同）
  2. 并行 + GPU 硬件编码
  3. 移动模式 + 硬件解码 + GPU 编码 + 并行（组合路径）
  4. 缩放 + 并行

运行：  .venv\\Scripts\\python.exe scripts\\verify_pipeline.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.encoder import (  # noqa: E402
    generate_sample_logo, generate_sample_video, process,
)
from app.models import (  # noqa: E402
    KIND_IMAGE, KIND_TEXT, MODE_MOTION, MODE_TILED,
    TRAJECTORY_FIGURE8, WatermarkConfig,
)

OUT = ROOT / "outputs"
failures = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


def md5(p: Path) -> str:
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(exist_ok=True)
    SRC = OUT / "pipe_sample.mp4"
    LOGO = OUT / "logo.png"
    if not SRC.exists():
        generate_sample_video(str(SRC), size=(640, 360), duration=2.0, fps=30)
    if not LOGO.exists():
        generate_sample_logo(str(LOGO), text="LOGO", size=220)

    cfg = WatermarkConfig(kind=KIND_TEXT, mode=MODE_TILED,
                          text="流水线测试", angle=20, text_opacity=90,
                          stroke_width=2)

    print("== 1. 串行 vs 并行输出字节级一致 ==")
    s1 = OUT / "pipe_serial.mp4"
    s4 = OUT / "pipe_parallel.mp4"
    process(str(SRC), str(s1), cfg, crf=23, preset="medium",
            hw_encoder="none", hw_decode=False, parallel=1)
    process(str(SRC), str(s4), cfg, crf=23, preset="medium",
            hw_encoder="none", hw_decode=False, parallel=4)
    check("串行/并行 MD5 一致", md5(s1) == md5(s4),
          f"{md5(s1)[:8]} vs {md5(s4)[:8]}")

    print("== 2. 并行 + GPU 编码 ==")
    s = process(str(SRC), str(OUT / "pipe_nvenc.mp4"), cfg, crf=23,
                preset="medium", hw_encoder="auto", hw_codec="h264",
                hw_decode=False, parallel=4)
    check("GPU+并行 帧数与编码器正确", s["frames"] == 60
          and s["codec"] == "h264_nvenc", f"codec={s.get('codec')} frames={s['frames']}")

    print("== 3. 移动模式 + 硬件解码 + GPU 编码 + 并行 ==")
    mc = WatermarkConfig(kind=KIND_IMAGE, image_path=str(LOGO),
                         mode=MODE_MOTION, motion_scale=0.15, motion_opacity=200,
                         img_radius=30, trajectory=TRAJECTORY_FIGURE8,
                         speed=1.0, motion_rotate=True, start_sec=0.5,
                         end_sec=1.5)
    s = process(str(SRC), str(OUT / "pipe_motion.mp4"), mc, crf=23,
                preset="medium", hw_encoder="auto", hw_codec="h264",
                hw_decode=True, parallel=4)
    check("移动+硬解+GPU+并行 正确", s["frames"] == 60
          and s["codec"] == "h264_nvenc", f"codec={s.get('codec')} frames={s['frames']}")

    print("== 4. 缩放 0.5 + 并行 ==")
    s = process(str(SRC), str(OUT / "pipe_scale.mp4"), cfg, crf=23,
                preset="medium", hw_encoder="none", hw_decode=False,
                scale=0.5, parallel=4)
    check("缩放0.5 输出 320x180", s["width"] == 320 and s["height"] == 180,
          f"{s['width']}x{s['height']}")

    print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
