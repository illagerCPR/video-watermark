"""硬件加速支持：GPU 编码器探测、编码/解码参数生成。

基于内置 imageio-ffmpeg 静态 ffmpeg（v7.1+，自带 NVENC / AMF / QSV / D3D12VA /
MediaFoundation 硬件编码器，零新增二进制）。本模块负责：

- `detect_encoders()`  探测当前机器可用的硬件编码器（对每个候选做一次极短样片
  实测编码，验证驱动/设备真的可用，结果缓存）；
- `resolve_encode()`   把统一的 CRF / 预设语义映射到各硬件编码器的等价参数，
  不可用时自动回退 libx264；
- `build_decode_input_params()`  硬件解码的 ffmpeg 输入参数。

设计要点：
- 零新增依赖、零新增二进制；PyInstaller onefile 打包流程不受影响。
- 任何硬件编码器不可用都不会让功能失效（自动回退 libx264）。
"""
from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

import imageio_ffmpeg

# ---------------------------------------------------------------------------
# 硬件编码器注册表
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HWEncoder:
    id: str                          # 内部 id：nvenc / qsv / amf / d3d12va / mf
    name: str                        # 显示名（中文）
    codecs: tuple[str, ...]          # 支持的视频编码类型（h264 / hevc / av1）

    def codec_name(self, vcodec: str) -> Optional[str]:
        """(编码器, 视频编码) -> ffmpeg 编码器名，如 ("nvenc","h264") -> h264_nvenc。"""
        if vcodec not in self.codecs:
            return None
        return f"{vcodec}_{self.id}"


_ENC_REGISTRY: tuple[HWEncoder, ...] = (
    HWEncoder("nvenc", "NVIDIA NVENC", ("h264", "hevc", "av1")),
    HWEncoder("qsv", "Intel QSV", ("h264", "hevc", "av1")),
    HWEncoder("amf", "AMD AMF", ("h264", "hevc", "av1")),
    HWEncoder("d3d12va", "Microsoft D3D12VA", ("hevc",)),
    HWEncoder("mf", "Microsoft MediaFoundation", ("h264", "hevc")),
)
ENC_IDS: dict[str, HWEncoder] = {e.id: e for e in _ENC_REGISTRY}

# auto 模式下的候选优先级（NVENC > QSV > AMF > D3D12VA > MF）
_AUTO_ORDER = ("nvenc", "qsv", "amf", "d3d12va", "mf")

# 可用的硬件编码器 id（GUI / CLI 可选值）
HW_ENCODER_IDS = ("auto", "none",) + _AUTO_ORDER
# 支持的视频编码类型
HW_CODECS = ("h264", "hevc")


# ---------------------------------------------------------------------------
# 探测
# ---------------------------------------------------------------------------


def _ffmpeg_encoder_names() -> set[str]:
    """从内置 ffmpeg 的 -encoders 输出中解析存在的编码器名集合。"""
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([exe, "-hide_banner", "-encoders"],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    names: set[str] = set()
    for line in r.stdout.splitlines():
        m = re.match(r"\s*\S+\s+(\S+)", line)  # 第二列为编码器名
        if m:
            names.add(m.group(1))
    return names


def _test_encoder(codec_name: str) -> bool:
    """对指定 ffmpeg 编码器做一次极短样片实测编码，验证驱动/设备可用。"""
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "t.mp4")
            cmd = [
                exe, "-y",
                "-f", "lavfi", "-i", "testsrc2=duration=0.4:size=320x240:rate=25",
                "-c:v", codec_name,
                "-b:v", "400k", "-pix_fmt", "yuv420p",
                out,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30)
            return (r.returncode == 0 and os.path.isfile(out)
                    and os.path.getsize(out) > 0)
    except Exception:  # noqa: BLE001
        return False


@functools.lru_cache(maxsize=1)
def detect_encoders() -> dict[str, tuple[str, ...]]:
    """探测可用硬件编码器。返回 {编码器id: 可用的视频编码元组}。

    结果按 ffmpeg 二进制版本持久化到磁盘（%APPDATA%/VideoWatermark/
    hw_encoders.json），每台机器只需完整探测一次；驱动或 ffmpeg 升级后
    自动失效重测。内存中再叠加 lru_cache，一次会话内多次调用零成本。
    """
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        st = os.stat(exe)
        key = (os.path.abspath(exe), st.st_size, int(st.st_mtime))
    except OSError:
        key = (imageio_ffmpeg.get_ffmpeg_exe(), 0, 0)

    cached = _load_cache(key)
    if cached is not None:
        return cached

    available = _detect_fresh()
    _save_cache(key, available)
    return available


def _detect_fresh() -> dict[str, tuple[str, ...]]:
    """完整探测（每个候选编码器做一次实测编码）。"""
    available: dict[str, tuple[str, ...]] = {}
    builtin = _ffmpeg_encoder_names()
    for enc in _ENC_REGISTRY:
        ok_codecs = []
        for vc in enc.codecs:
            cn = enc.codec_name(vc)
            if cn in builtin and _test_encoder(cn):
                ok_codecs.append(vc)
        if ok_codecs:
            available[enc.id] = tuple(ok_codecs)
    return available


def _cache_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "VideoWatermark", "hw_encoders.json")


def _load_cache(key) -> Optional[dict[str, tuple[str, ...]]]:
    """读取磁盘缓存；key 不匹配或损坏返回 None。"""
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("key") != list(key):
            return None
        raw = data.get("encoders") or {}
        out = {}
        for eid, codecs in raw.items():
            if eid in ENC_IDS and isinstance(codecs, list):
                out[eid] = tuple(c for c in codecs if c in ENC_IDS[eid].codecs)
        return out or None
    except (OSError, ValueError, TypeError):
        return None


def _save_cache(key, available: dict) -> None:
    """把探测结果写入磁盘缓存（尽力而为，失败静默忽略）。"""
    try:
        path = _cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"key": list(key),
                       "encoders": {k: list(v) for k, v in available.items()}},
                      f, ensure_ascii=False)
    except OSError:
        pass


def describe_available() -> str:
    """人类可读的可用硬件编码器描述（GUI 提示用）。"""
    avail = detect_encoders()
    if not avail:
        return "未检测到可用硬件编码器（将使用 CPU 编码 libx264）"
    parts = []
    for eid in _AUTO_ORDER:
        if eid in avail:
            parts.append(f"{ENC_IDS[eid].name}（{'/'.join(avail[eid])}）")
    return "检测到可用硬件编码器：" + "、".join(parts)


# ---------------------------------------------------------------------------
# 编码参数映射
# ---------------------------------------------------------------------------

# x264 预设名 -> 各硬件编码器预设（None 表示该编码器不适用，跳过）
_X264_TO_HW_PRESET: dict[str, dict[str, Optional[str]]] = {
    "ultrafast": {"nvenc": "p1", "qsv": "veryfast", "amf": "speed", "mf": "speed"},
    "superfast": {"nvenc": "p2", "qsv": "veryfast", "amf": "speed", "mf": "speed"},
    "veryfast":  {"nvenc": "p3", "qsv": "veryfast", "amf": "speed", "mf": "speed"},
    "faster":    {"nvenc": "p4", "qsv": "faster",   "amf": "speed", "mf": "speed"},
    "fast":      {"nvenc": "p4", "qsv": "fast",     "amf": "balanced", "mf": "speed"},
    "medium":    {"nvenc": "p5", "qsv": "medium",   "amf": "balanced", "mf": "balanced"},
    "slow":      {"nvenc": "p6", "qsv": "slow",     "amf": "quality",  "mf": "balanced"},
    "slower":    {"nvenc": "p6", "qsv": "slower",   "amf": "quality",  "mf": "quality"},
    "veryslow":  {"nvenc": "p7", "qsv": "veryslow", "amf": "quality",  "mf": "quality"},
}


def _estimate_bitrate(w: int, h: int, fps: float, crf: int) -> str:
    """把 x264 CRF（0~51，越小越好）近似换算成码率，供不支持 CRF 的编码器使用。

    经验公式：以 1080p30@crf23≈4Mbps 为基准，crf 每降 6 档码率翻倍。
    """
    factor = 2 ** ((23 - crf) / 6.0)
    kbps = 0.07 * w * h * fps / 1000.0 * factor
    return f"{int(max(200, kbps))}k"


def build_hw_output_params(enc_id: str, vcodec: str, crf: int, preset: str,
                           w: int, h: int, fps: float) -> list[str]:
    """生成某硬件编码器与视频编码对应的 ffmpeg 输出参数（CRF/预设映射）。"""
    crf = max(0, min(51, int(crf)))
    mapping = _X264_TO_HW_PRESET.get((preset or "medium").lower(),
                                     _X264_TO_HW_PRESET["medium"])
    if enc_id == "nvenc":
        # 恒定 QP 最贴近 CRF 的"恒定质量"语义，且实测比 -rc vbr -cq 快数倍
        return ["-rc", "constqp", "-qp", str(crf), "-preset", mapping["nvenc"]]
    if enc_id == "qsv":
        return ["-global_quality", str(crf), "-preset", mapping["qsv"]]
    if enc_id == "amf":
        qp = str(crf)
        return ["-quality", mapping["amf"], "-rc", "cqp",
                "-qp_i", qp, "-qp_p", qp]
    if enc_id == "d3d12va":
        return ["-rc", "vbr", "-qp", str(crf)]
    if enc_id == "mf":
        return ["-b:v", _estimate_bitrate(w, h, fps, crf)]
    return []


def resolve_encode(hw_encoder: str, vcodec: str, crf: int, preset: str,
                   w: int, h: int, fps: float) -> tuple[str, list[str]]:
    """返回 (ffmpeg 编码器名, 输出参数列表)；不可用或失败时回退 libx264。

    hw_encoder: "auto" / "none" / 编码器 id（nvenc/qsv/amf/d3d12va/mf）
    vcodec:     "h264" / "hevc"（仅硬件编码器生效；libx264 固定输出 H.264）
    """
    vcodec = vcodec.lower()
    if vcodec not in HW_CODECS:
        vcodec = "h264"
    crf = max(0, min(51, int(crf)))
    preset = preset or "medium"
    x264_params = ["-crf", str(crf), "-preset", preset]

    # 关闭硬件编码 -> 直接走 libx264（H.264）
    if hw_encoder in (None, "", "none"):
        return "libx264", x264_params

    available = detect_encoders()

    # 自动：按优先级挑第一个可用且支持目标编码的硬件编码器
    if hw_encoder == "auto":
        for eid in _AUTO_ORDER:
            if eid in available and vcodec in available[eid]:
                return ENC_IDS[eid].codec_name(vcodec), build_hw_output_params(
                    eid, vcodec, crf, preset, w, h, fps)
        return "libx264", x264_params

    # 明确指定某硬件编码器：不可用则报错（不静默回退，便于用户发现）
    enc = ENC_IDS.get(hw_encoder)
    if enc is None:
        raise ValueError(f"未知硬件编码器：{hw_encoder}")
    if hw_encoder not in available or vcodec not in available[hw_encoder]:
        raise RuntimeError(
            f"{enc.name} 硬件编码器不可用（{vcodec}）。当前可用："
            f"{describe_available()}。请改用 auto 或关闭硬件编码。")
    return enc.codec_name(vcodec), build_hw_output_params(
        hw_encoder, vcodec, crf, preset, w, h, fps)


# ---------------------------------------------------------------------------
# 硬件解码
# ---------------------------------------------------------------------------


def build_decode_input_params(enable: bool) -> list[str]:
    """硬件解码的 ffmpeg 输入参数；enable=False 返回空列表（纯软件解码）。

    `-hwaccel auto` 在 Windows 上自动挑选 d3d11va / dxva2 / qsv / cuda，
    仅加速解码环节；输出仍经 rawvideo 转回 RGB 帧，行为与软解一致。
    """
    if not enable:
        return []
    return ["-hwaccel", "auto"]


__all__ = [
    "HWEncoder", "ENC_IDS", "HW_ENCODER_IDS", "HW_CODECS",
    "detect_encoders", "describe_available",
    "resolve_encode", "build_hw_output_params",
    "build_decode_input_params",
]
