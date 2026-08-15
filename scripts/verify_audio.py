# -*- coding: utf-8 -*-
"""验证音频保留：有音频的输入 -> 输出必须保留音频流。"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.encoder import (  # noqa: E402
    generate_sample_video, get_ffmpeg_exe, probe, process,
)
from app.models import WatermarkConfig  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outputs")
os.makedirs(OUT, exist_ok=True)


def streams_info(path):
    exe = get_ffmpeg_exe()
    r = subprocess.run([exe, "-i", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stderr


def check_audio(path, expect=True):
    stderr = streams_info(path)
    has = "Audio:" in stderr
    tag = "有音频" if has else "无音频"
    status = "OK" if has == expect else "FAIL"
    print(f"  [{status}] {os.path.basename(path)} -> {tag}"
          + ("" if status == "OK" else f" (期望 expect={expect})"))
    if status == "FAIL":
        return False
    return True


def main():
    exe = get_ffmpeg_exe()

    # 1) 带音频的输入
    src_audio = os.path.join(OUT, "audio_src.mp4")
    if not os.path.exists(src_audio):
        print("生成带音频的样片...")
        generate_sample_video(src_audio, duration=3.0)
    print("输入（带音频）流信息：")
    print("\n".join("   " + l for l in streams_info(src_audio).splitlines()
                    if "Stream" in l))
    ok = check_audio(src_audio, expect=True)
    if not ok:
        print("输入样片本身无音频，无法继续。")
        return 1

    # 2) 处理并保留音频
    out_audio = os.path.join(OUT, "audio_out.mp4")
    cfg = WatermarkConfig(mode="tiled", kind="text", text="音频测试")
    print(f"处理 -> {os.path.basename(out_audio)} ...")
    process(src_audio, out_audio, cfg, crf=23, preset="veryfast")
    print("输出流信息：")
    print("\n".join("   " + l for l in streams_info(out_audio).splitlines()
                    if "Stream" in l))
    ok = check_audio(out_audio, expect=True) and ok

    # 3) 无音频的输入也应正常（不报错）
    src_vo = os.path.join(OUT, "voiceonly_src.mp4")
    if not os.path.exists(src_vo):
        print("生成无音频的样片...")
        generate_sample_video(src_vo, duration=3.0, with_audio=False)
    out_vo = os.path.join(OUT, "voiceonly_out.mp4")
    print(f"处理 -> {os.path.basename(out_vo)} ...")
    process(src_vo, out_vo, cfg, crf=23, preset="veryfast")
    print("输出流信息：")
    print("\n".join("   " + l for l in streams_info(out_vo).splitlines()
                    if "Stream" in l))
    ok = check_audio(out_vo, expect=False) and ok

    # 4) probe 的 has_audio 字段
    m1, m2 = probe(src_audio), probe(out_audio)
    print(f"probe 输入 has_audio={m1['has_audio']}, 输出 has_audio={m2['has_audio']}")
    ok = (m1["has_audio"] and m2["has_audio"]) and ok

    print("\n结论:", "全部通过 ✅" if ok else "存在失败 ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
