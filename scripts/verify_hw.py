"""硬件加速验证脚本：探测 + 各可用硬件编码器实跑 + 自动回退 + 硬件解码 + 音频保留。

运行：  .venv\\Scripts\\python.exe scripts\\verify_hw.py
覆盖：
  1. detect_encoders() 探测结果
  2. auto 模式（应选中硬件编码器，无 GPU 则回退 libx264）
  3. 每种可用硬件编码器分别实跑编码（NVENC / QSV / AMF / D3D12VA / MF）
  4. 显式指定不可用编码器应报错（带清晰提示）
  5. 硬件解码路径（-hwaccel auto）
  6. 硬件编码 + 音频保留合并
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import imageio_ffmpeg  # noqa: E402

from app.core import hwaccel  # noqa: E402
from app.core.encoder import (  # noqa: E402
    generate_sample_logo, generate_sample_video, process,
)
from app.models import KIND_TEXT, MODE_TILED, WatermarkConfig  # noqa: E402

OUT = ROOT / "outputs"
SAMPLE = OUT / "hw_sample.mp4"
LOGO = OUT / "logo.png"

failures = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


def has_audio(path) -> bool:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([exe, "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return "Audio:" in r.stderr


def main() -> int:
    OUT.mkdir(exist_ok=True)
    generate_sample_video(str(SAMPLE), size=(640, 360), duration=2.0, fps=30,
                          with_audio=True)
    generate_sample_logo(str(LOGO), text="HW", size=120)
    cfg = WatermarkConfig(kind=KIND_TEXT, mode=MODE_TILED,
                          text="硬件加速测试", angle=20,
                          text_opacity=90, stroke_width=2)

    print("== 1. 探测可用硬件编码器 ==")
    avail = hwaccel.detect_encoders()
    print("   ", avail)
    check("探测结果含 nvenc（本机为 RTX 4050）",
          "nvenc" in avail and "h264" in avail.get("nvenc", ()), f"{avail}")

    print("== 2. auto 模式（应选中硬件编码器或回退 libx264）==")
    s = process(str(SAMPLE), str(OUT / "hw_auto.mp4"), cfg,
                hw_encoder="auto", hw_codec="h264", hw_decode=False)
    print(f"    选用编码器：{s.get('codec')}")
    check("auto 输出有效", os.path.getsize(OUT / "hw_auto.mp4") > 0,
          f"codec={s.get('codec')}")
    check("auto 音频保留", has_audio(OUT / "hw_auto.mp4"))

    print("== 3. 各可用硬件编码器分别实跑 ==")
    ran = 0
    for eid in ("nvenc", "qsv", "amf", "d3d12va", "mf"):
        if eid not in avail:
            print(f"    - {eid} 不可用，跳过")
            continue
        vc = avail[eid][0]  # 每种编码器测首选编码
        out = OUT / f"hw_{eid}.mp4"
        st = process(str(SAMPLE), str(out), cfg,
                     hw_encoder=eid, hw_codec=vc, hw_decode=False)
        check(f"{eid}/{vc} 编码成功", os.path.getsize(out) > 0,
              f"codec={st.get('codec')}")
        check(f"{eid}/{vc} 音频保留", has_audio(out))
        ran += 1
    check("至少一个硬件编码器实跑成功", ran >= 1, f"实跑 {ran} 个")

    print("== 4. 显式指定不可用编码器应报错 ==")
    unavailable = next((e for e in ("nvenc", "qsv", "amf", "d3d12va", "mf")
                        if e not in avail), None)
    if unavailable is None:
        # 全部可用（不可能发生，除非驱动装了全部三家）——则测一个假 id
        bad_id = "nvenc"
    else:
        bad_id = unavailable
    try:
        process(str(SAMPLE), str(OUT / "hw_bad.mp4"), cfg,
                hw_encoder=bad_id, hw_codec="h264", hw_decode=False)
        check(f"指定不可用编码器 {bad_id} 应报错", False, "未报错")
    except RuntimeError as exc:
        check(f"指定不可用编码器 {bad_id} 应报错", True, str(exc)[:60])
    except Exception as exc:  # noqa: BLE001
        check(f"指定不可用编码器 {bad_id} 应报错", False,
              f"异常类型不对: {type(exc).__name__}")

    print("== 5. 硬件解码路径（-hwaccel auto）==")
    s5 = process(str(SAMPLE), str(OUT / "hw_decode.mp4"), cfg,
                 hw_encoder="auto", hw_codec="h264", hw_decode=True)
    check("硬件解码(自动) 成功", os.path.getsize(OUT / "hw_decode.mp4") > 0,
          f"codec={s5.get('codec')}")

    print("== 6. 硬件编码 + 硬件解码 + 音频（全链路）==")
    s6 = process(str(SAMPLE), str(OUT / "hw_full.mp4"), cfg,
                 hw_encoder="auto", hw_codec="h264", hw_decode=True)
    check("全链路输出有效", os.path.getsize(OUT / "hw_full.mp4") > 0,
          f"codec={s6.get('codec')}")
    check("全链路音频保留", has_audio(OUT / "hw_full.mp4"))

    print("== 7. 关闭硬件（纯 CPU libx264）==")
    s7 = process(str(SAMPLE), str(OUT / "hw_none.mp4"), cfg,
                 hw_encoder="none", hw_codec="h264", hw_decode=False)
    check("纯 CPU 输出有效", s7.get("codec") == "libx264"
          and os.path.getsize(OUT / "hw_none.mp4") > 0, f"codec={s7.get('codec')}")

    print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
