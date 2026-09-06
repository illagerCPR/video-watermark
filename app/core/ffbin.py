"""ffmpeg 可执行文件解析层（v0.3.2 起）。

统一决定全项目使用哪个 ffmpeg 二进制，并经 imageio-ffmpeg 的官方覆写点
IMAGEIO_FFMPEG_EXE 生效——encoder.py / hwaccel.py 中所有 ffmpeg 取用
自动跟随切换，编码/探测逻辑零改动。

背景：imageio-ffmpeg 随包分发的 Linux 版静态 ffmpeg 未编译任何硬件编码
器（-encoders 中无 *_nvenc/_qsv 等），Windows 版自带全套。本层在不破坏
"零系统依赖"卖点的前提下恢复 Linux 的 GPU 能力：

优先级：
1. 显式指定：环境变量 VIDEO_WATERMARK_FFMPEG（CLI `--ffmpeg` 写入）。
   - `internal`：强制使用内置二进制；
   - 其余按路径解析并校验可运行，失败直接抛错（显式指定不静默回退）。
   （优先于 IMAGEIO_FFMPEG_EXE：应用层显式覆写更具体，且批量并行等
   子进程会继承两个变量，须保证显式意图不被子进程继承关系稀释。）
2. 用户已自行设置 imageio 官方覆写点 IMAGEIO_FFMPEG_EXE —— 尊重之。
3. 自动选择：内置二进制缺硬件编码器（Linux 常态）时，探测系统 ffmpeg
   （shutil.which）若编译了硬件编码器（nvenc/qsv/amf/mf/d3d12va）则
   启用之；否则维持内置二进制（零依赖、行为可预期）。
   Windows 内置二进制自带全套硬件编码器，自动分支天然不触发。

解析结果进程内缓存（lru_cache），决策详情见 info()。任何自动分支的
意外异常都回退内置二进制，绝不影响启动。
"""
from __future__ import annotations

import functools
import os
import re
import shutil

import imageio_ffmpeg

from .subproc import run as run_hidden

# 本模块的显式覆写环境变量（CLI --ffmpeg / 用户手动设置均可）
OVERRIDE_ENV = "VIDEO_WATERMARK_FFMPEG"
# imageio-ffmpeg 的官方覆写点（get_ffmpeg_exe() 每次调用都会读取它）
_IMAGEIO_ENV = "IMAGEIO_FFMPEG_EXE"

# 判定"具备硬件编码能力"的编码器名后缀（可接受软件帧直接编码的家族；
# vaapi 需要滤镜链暂不支持，不参与切换判定）
_HW_SUFFIX = re.compile(r"_(nvenc|qsv|amf|mf|d3d12va)$")

_info: dict = {"exe": None, "source": "未解析", "note": ""}


def bundled_exe() -> str:
    """返回 imageio-ffmpeg 随包分发的二进制路径（忽略一切环境变量）。

    自检用它验证打包完整性——无论 ffbin 最终选了哪个二进制，
    "内置文件存在且可运行"必须独立成立。
    """
    saved = os.environ.pop(_IMAGEIO_ENV, None)
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    finally:
        if saved is not None:
            os.environ[_IMAGEIO_ENV] = saved


def encoder_names(exe: str) -> set[str]:
    """解析指定 ffmpeg 二进制 `-encoders` 输出中的编码器名集合。"""
    try:
        r = run_hidden([exe, "-hide_banner", "-encoders"],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    except Exception:  # noqa: BLE001
        return set()
    names: set[str] = set()
    for line in r.stdout.splitlines():
        m = re.match(r"\s*\S+\s+(\S+)", line)  # 第二列为编码器名
        if m:
            names.add(m.group(1))
    return names


def _hw_names(names: set[str]) -> set[str]:
    return {n for n in names if _HW_SUFFIX.search(n)}


def _runnable(exe: str) -> bool:
    try:
        r = run_hidden([exe, "-version"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=30)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _use(exe: str, source: str, note: str = "") -> str:
    exe = os.path.abspath(exe)
    os.environ[_IMAGEIO_ENV] = exe  # 透传给 imageio-ffmpeg 全部调用
    _info.update(exe=exe, source=source, note=note)
    return exe


@functools.lru_cache(maxsize=1)
def get_ffmpeg_exe() -> str:
    """解析最终使用的 ffmpeg 可执行文件（进程内缓存，首次调用时决策）。"""
    # 1) 显式指定（CLI --ffmpeg / VIDEO_WATERMARK_FFMPEG），优先级最高：
    #    子进程（批量并行）会同时继承本变量与 IMAGEIO_FFMPEG_EXE，
    #    显式意图必须压过继承来的镜像值。
    explicit = os.environ.get(OVERRIDE_ENV)
    if explicit:
        if explicit.strip().lower() == "internal":
            return _use(bundled_exe(), "内置二进制（--ffmpeg internal 强制）")
        path = os.path.expanduser(explicit)
        if not _runnable(path):
            raise RuntimeError(
                f"--ffmpeg 指定的 ffmpeg 不可运行：{path}（"
                f"可传 internal 强制使用内置二进制）")
        return _use(path, f"显式指定（{OVERRIDE_ENV}）")

    # 2) 用户已自行设置 imageio 官方覆写点：尊重之（不校验，与 imageio 行为一致）
    user_env = os.environ.get(_IMAGEIO_ENV)
    if user_env:
        return _use(user_env, "IMAGEIO_FFMPEG_EXE（用户设置）")

    # 3) 自动选择：内置缺硬件编码器时尝试系统 ffmpeg
    try:
        inner = bundled_exe()
        inner_hw = _hw_names(encoder_names(inner))
        if inner_hw:
            return _use(inner, "内置二进制",
                        "自带硬件编码器: " + ",".join(sorted(inner_hw)[:4]))

        sys_ffmpeg = shutil.which("ffmpeg")
        if sys_ffmpeg:
            sys_hw = _hw_names(encoder_names(sys_ffmpeg))
            gained = sys_hw - inner_hw
            if gained and _runnable(sys_ffmpeg):
                return _use(sys_ffmpeg, "系统 ffmpeg（自动切换）",
                            "新增硬件编码器: " + ",".join(sorted(gained)[:4]))
        return _use(inner, "内置二进制", "无可用硬件编码器，将使用 CPU 编码")
    except Exception:  # noqa: BLE001  # 自动分支绝不影响启动
        return _use(bundled_exe(), "内置二进制", "自动选择异常，已回退")


def info() -> dict:
    """最近一次解析的决策信息：{exe, source, note}。"""
    if _info["exe"] is None:
        get_ffmpeg_exe()
    return dict(_info)
