"""验收验证：时间范围演示 —— 范围外无水印，范围内有水印。

对 accept_motion_range.mp4：
  - t=0.2s（范围前）与原片对比 几乎无差异
  - t=2.0s（范围内）与原片对比 有明显差异
"""
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
sys.path.insert(0, str(ROOT))

failures = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


def frame_diff(video_a, video_b, idx, fps=30):
    def grab(video, target):
        gen = imageio_ffmpeg.read_frames(str(OUT / video), pix_fmt="rgb24")
        next(gen)
        fr = None
        for i, fb in enumerate(gen):
            if i == target:
                fr = Image.frombytes("RGB", (640, 360), fb)
                break
        gen.close()
        return fr

    a, b = grab(video_a, idx), grab(video_b, idx)
    pa, pb = a.load(), b.load()
    changed = 0
    # 阈值 120：隔离水印造成的强差异，过滤 re-encode 噪声（通常每通道差几个单位）
    for y in range(360):
        for x in range(640):
            ra, ga, ba = pa[x, y]
            rb, gb, bb = pb[x, y]
            if abs(ra - rb) + abs(ga - gb) + abs(ba - bb) > 120:
                changed += 1
    return changed


SRC = "sample_video.mp4"
TGT = "accept_motion_range.mp4"

# 范围前 t=0.2s -> 帧 6
d_before = frame_diff(SRC, TGT, 6)
check("t=0.2s(范围前)无水印", d_before < 300, f"强差异像素={d_before}")
# 范围内 t=2.0s -> 帧 60
d_in = frame_diff(SRC, TGT, 60)
check("t=2.0s(范围内)有水印", d_in > 1000, f"强差异像素={d_in}")
# 范围后 t=4.5s -> 帧 135
d_after = frame_diff(SRC, TGT, 135)
check("t=4.5s(范围后)无水印", d_after < 300, f"强差异像素={d_after}")

print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
sys.exit(1 if failures else 0)
