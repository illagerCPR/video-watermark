"""视频读写与编码：基于 imageio-ffmpeg 内置静态 ffmpeg，免系统安装。

- probe()           探测视频宽高 / 帧率 / 时长
- process()         读输入帧 -> 合成水印 -> 编码输出（带进度回调）
- generate_sample_video()  生成测试样片（便于无输入视频时验证）
- generate_sample_logo()   生成测试 logo 图片（验证图片水印）
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont

import imageio_ffmpeg

from ..models import WatermarkConfig
from .compositor import WatermarkCompositor

ProgressCB = Optional[Callable[[int, int], None]]  # (done, total)


def get_ffmpeg_exe() -> str:
    """返回内置 ffmpeg 可执行文件路径；首次使用会自动下载静态二进制。"""
    return imageio_ffmpeg.get_ffmpeg_exe()


# ---------------------------------------------------------------------------
# 探测
# ---------------------------------------------------------------------------

def probe(path: str) -> dict:
    """返回 {width, height, fps, frames, duration_sec}。"""
    exe = get_ffmpeg_exe()
    r = subprocess.run([exe, "-i", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    stderr = r.stderr

    size_m = re.search(r"(\d{2,5})x(\d{2,5})", stderr)
    width = int(size_m.group(1)) if size_m else 0
    height = int(size_m.group(2)) if size_m else 0

    fps = 0.0
    fps_m = re.search(r"(\d+(?:\.\d+)?) fps", stderr)
    if fps_m:
        fps = float(fps_m.group(1))
    if not fps_m:
        tbr_m = re.search(r"(\d+(?:\.\d+)?) tbr", stderr)
        if tbr_m:
            fps = float(tbr_m.group(1))

    dur = 0.0
    dur_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if dur_m:
        dur = int(dur_m.group(1)) * 3600 + int(dur_m.group(2)) * 60 + float(dur_m.group(3))

    frames = int(round(dur * fps)) if (dur and fps) else 0
    if width == 0 or fps == 0:
        raise RuntimeError(f"无法解析视频信息：{path}\n{stderr[-500:]}")
    return {"width": width, "height": height, "fps": fps,
            "frames": frames, "duration_sec": dur,
            "has_audio": bool(re.search(r"Audio:\s*\S+", stderr))}


# ---------------------------------------------------------------------------
# 主处理流程
# ---------------------------------------------------------------------------

def process(input_path: str, output_path: str, cfg: WatermarkConfig,
            progress_cb: ProgressCB = None,
            crf: int = 23, preset: str = "medium",
            scale: float = 1.0, out_fps: Optional[float] = None,
            pix_fmt_out: str = "yuv420p") -> dict:
    """读输入视频 -> 逐帧叠加水印 -> 编码输出，并保留原音频。

    视频帧通过 imageio-ffmpeg 逐帧处理；音频流用内置 ffmpeg 从原视频
    无损复制（copy）合并回输出，保证转换后不丢音轨。
    返回处理统计 {frames, width, height, fps}。
    """
    meta = probe(input_path)
    W, H = meta["width"], meta["height"]
    fps = meta["fps"]
    total = meta["frames"] or 0

    out_w = max(2, int(round(W * scale))) if scale and scale != 1.0 else W
    out_h = max(2, int(round(H * scale))) if scale and scale != 1.0 else H
    # 只对齐到偶数（yuv420p 要求），保持原始分辨率不拉伸；
    # 配合 macro_block_size=1，让 imageio-ffmpeg 不做内部二次缩放
    if out_w % 2:
        out_w += 1
    if out_h % 2:
        out_h += 1

    comp = WatermarkCompositor(cfg, out_w, out_h, fps)

    out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    suffix = os.path.splitext(output_path)[1] or ".mp4"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix=".vw_tmp_", dir=out_dir)
    os.close(fd)

    done = 0
    writer = imageio_ffmpeg.write_frames(
        tmp_path,
        (out_w, out_h),
        pix_fmt_in="rgb24",
        pix_fmt_out=pix_fmt_out,
        fps=out_fps or fps,
        codec="libx264",
        macro_block_size=1,
        output_params=["-crf", str(crf), "-preset", preset],
    )
    writer.send(None)  # 启动写入生成器（imageio-ffmpeg 约定）
    try:
        gen = imageio_ffmpeg.read_frames(input_path, pix_fmt="rgb24")
        next(gen)  # 首个产出为元数据 dict，跳过
        for frame_bytes in gen:
            img = Image.frombytes("RGB", (W, H), frame_bytes)
            if (out_w, out_h) != (W, H):
                img = img.resize((out_w, out_h), Image.LANCZOS)
            t = done / fps
            comp.apply(img, t)
            writer.send(img.tobytes())
            done += 1
            if progress_cb:
                progress_cb(done, total)
    finally:
        writer.close()

    try:
        _merge_audio(input_path, tmp_path, output_path, fps_out=out_fps or fps)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {"frames": done, "width": out_w, "height": out_h, "fps": fps}


# ---------------------------------------------------------------------------
# 音频保留
# ---------------------------------------------------------------------------

def _merge_audio(input_path: str, video_tmp: str, output_path: str,
                 fps_out: float) -> None:
    """把原视频的音频流合并到已处理的无音频视频上。

    - 输入有音频：`-map 1:a:0` 复制原音频流（`-c:a copy` 无损），
      时长对齐（-shortest），保证视频与音频同步。
    - 输入无音频：直接改名输出（纯视频）。
    """
    exe = get_ffmpeg_exe()
    r = subprocess.run([exe, "-i", input_path], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if "Audio:" not in r.stderr:
        # 原视频没有音频流 -> 直接以视频文件收尾
        os.replace(video_tmp, output_path)
        return

    # 有音频：视频取已处理帧，音频从原视频复制；时长取两者较短
    cmd = [
        exe, "-y",
        "-i", video_tmp,          # 0: 已加水的视频（无音频）
        "-i", input_path,         # 1: 原视频（含音频）
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "copy",
        "-shortest",
        output_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if res.returncode == 0:
        return

    # 容器不兼容原音频编码（如 vorbis/opus 放入 mp4）时，回退重编码为 AAC
    fallback = [
        exe, "-y",
        "-i", video_tmp,
        "-i", input_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    res2 = subprocess.run(fallback, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if res2.returncode != 0:
        raise RuntimeError(
            f"音频合并失败：{res2.stderr[-500:]}")


# ---------------------------------------------------------------------------
# 测试素材生成
# ---------------------------------------------------------------------------

def generate_sample_video(path: str, size: tuple = (640, 360),
                          duration: float = 5.0, fps: int = 30,
                          with_audio: bool = True) -> None:
    """用 lavfi 生成一段彩色动态样片（含 H.264 视频，可选音频）。"""
    exe = get_ffmpeg_exe()
    w, h = size
    cmd = [
        exe, "-y",
        "-f", "lavfi", "-i",
        f"testsrc2=duration={duration}:size={w}x{h}:rate={fps}",
    ]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "23", "-preset", "medium"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd.append(path)
    subprocess.run(cmd, check=True, capture_output=True)


def generate_sample_logo(path: str, text: str = "LOGO", size: int = 220) -> None:
    """生成一张带圆角与透明度的测试 logo PNG。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 背景：半透明圆角矩形
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5,
                        fill=(255, 82, 82, 200))
    try:
        font = ImageFont.truetype("arialbd.ttf", size // 4)
    except OSError:
        font = ImageFont.load_default(size // 4)
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2, (size - th) / 2 - bbox[1]), text, font=font,
           fill=(255, 255, 255, 255))
    img.save(path)


__all__ = ["get_ffmpeg_exe", "probe", "process",
           "generate_sample_video", "generate_sample_logo"]
