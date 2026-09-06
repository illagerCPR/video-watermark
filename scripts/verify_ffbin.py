"""ffbin 解析层专项验证：显式指定 / internal / 环境变量优先级 / 自动回退。

运行：  PYTHONIOENCODING=utf-8 .venv/bin/python scripts/verify_ffbin.py
        （Windows: .venv\\Scripts\\python.exe scripts\\verify_ffbin.py）

覆盖（每个用例用受控环境的子进程隔离 lru_cache）：
  1. 默认干净环境：解析成功、二进制可运行、info() 结构完整
  2. internal 强制内置：结果 == bundled_exe()
  3. 显式有效路径：切换生效（用系统 ffmpeg 或内置二进制自身充当"外部"路径）
  4. 显式无效路径：RuntimeError（不静默回退）
  5. 仅 IMAGEIO_FFMPEG_EXE：尊重用户设置
  6. 双变量并存（模拟子进程继承）：VIDEO_WATERMARK_FFMPEG 压过 IMAGEIO_FFMPEG_EXE
  7. detect_encoders() 联动：ffbin 切换后 hwaccel 探测正常（结果任意）
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core import ffbin  # noqa: E402

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


def run_py(code: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """在受控环境的子进程里执行代码（环境只保留 PATH 级基础变量）。"""
    env = {"PATH": os.environ.get("PATH", ""),
           "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
           "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", ""),
           "PYTHONIOENCODING": "utf-8"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def main() -> int:
    bundled = ffbin.bundled_exe()

    # 1) 默认环境
    r = run_py("from app.core import ffbin\n"
               "exe = ffbin.get_ffmpeg_exe()\n"
               "i = ffbin.info()\n"
               "import os; print(int(os.path.isfile(exe)), i['exe'] == exe, "
               "bool(i['source']))")
    out = r.stdout.strip()
    check("默认环境解析成功且 info 完整", r.returncode == 0 and out == "1 True True", out)

    # 2) internal 强制内置
    r = run_py("from app.core import ffbin\n"
               "print(ffbin.get_ffmpeg_exe() == ffbin.bundled_exe())",
               {"VIDEO_WATERMARK_FFMPEG": "internal"})
    check("internal 强制内置", r.returncode == 0 and r.stdout.strip() == "True")

    # 3) 显式有效路径（拿内置二进制自身当"外部"路径，全平台可复现）
    r = run_py("from app.core import ffbin\n"
               "print(ffbin.info()['source'])",
               {"VIDEO_WATERMARK_FFMPEG": ffbin.bundled_exe()})
    check("显式有效路径生效", r.returncode == 0
          and "显式指定" in r.stdout.strip(), r.stdout.strip())

    # 4) 显式无效路径 → RuntimeError
    r = run_py("from app.core import ffbin\n"
               "try:\n"
               "    ffbin.get_ffmpeg_exe()\n"
               "    print('NO_ERROR')\n"
               "except RuntimeError:\n"
               "    print('ERROR_AS_EXPECTED')",
               {"VIDEO_WATERMARK_FFMPEG": str(Path("__nonexistent__") / "ffmpeg")})
    check("显式无效路径报错", r.returncode == 0
          and r.stdout.strip() == "ERROR_AS_EXPECTED", r.stdout.strip())

    # 5) 仅 IMAGEIO_FFMPEG_EXE → 尊重
    r = run_py("from app.core import ffbin\n"
               "print(ffbin.get_ffmpeg_exe(), '|', ffbin.info()['source'])",
               {"IMAGEIO_FFMPEG_EXE": ffbin.bundled_exe()})
    check("尊重 IMAGEIO_FFMPEG_EXE", r.returncode == 0
          and "IMAGEIO_FFMPEG_EXE" in r.stdout, r.stdout.strip())

    # 6) 双变量并存：显式意图压过继承的镜像值（无效路径应报错而非被镜像值救回）
    r = run_py("from app.core import ffbin\n"
               "try:\n"
               "    ffbin.get_ffmpeg_exe()\n"
               "    print('NO_ERROR')\n"
               "except RuntimeError:\n"
               "    print('ERROR_AS_EXPECTED')",
               {"VIDEO_WATERMARK_FFMPEG": str(Path("__nonexistent__") / "ffmpeg"),
                "IMAGEIO_FFMPEG_EXE": ffbin.bundled_exe()})
    check("双变量并存时显式意图优先", r.returncode == 0
          and r.stdout.strip() == "ERROR_AS_EXPECTED", r.stdout.strip())

    # 7) 与 hwaccel 联动（当前环境探测一次，结果任意但不得抛异常）
    try:
        from app.core import hwaccel
        det = hwaccel.detect_encoders()
        check("detect_encoders 联动正常", isinstance(det, dict), str(det))
    except Exception as exc:  # noqa: BLE001
        check("detect_encoders 联动正常", False, repr(exc))

    print()
    if failures:
        print(f"失败 {len(failures)} 项: {failures}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
