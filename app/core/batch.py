"""批量处理核心（v0.5.6 起 GUI/TUI 共用后端）：多视频用同一套水印参数批量生成。

- scan_videos(path)：路径为文件直接用；为目录则递归扫描视频扩展名（排序）
- plan_jobs(inputs, out_dir, out_ext)：生成 (输入, 输出) 任务列表，命名「原名_水印.扩展名」
- run_batch(...)：串行 / 并行（进程池）统一入口，支持逐文件帧进度回调与取消

并行模式说明（改这里必读）：
- 子进程里的逐帧进度经 ``multiprocessing.Manager().Queue`` 传回父进程转发线程；
  **Manager 及其 Queue 必须在 UI 主线程创建后作 progress_q 传入**（Windows 下
  非主线程创建 Queue 会 WinError 5），创建失败时传 None = 并行无帧进度，不阻断。
- 取消：threading.Event 不可跨进程 pickle，并行模式下取消 = 停止提交后续任务、
  等待在途文件处理完；串行模式下取消可中断当前文件（process 的 cancel_event）。
- 进程池提交采用**有界提交**（保持 ≤ batch_parallel 个在途），取消后不再提交。
- export_params 不透传 parallel（帧流水线保持 process() 默认 auto），与 GUI 批量一致。
- 顶层函数 _run_one 必须可 pickle（Windows spawn）；本模块顶层不得有重活。
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import threading
from pathlib import Path

from .encoder import ProcessCancelled, process
from ..models import WatermarkConfig

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".ts"}

# 跨进程帧进度回传的结束哨兵（字符串保证经过队列 pickle 往返后仍可比较）
PROGRESS_END = "__BATCH_PROGRESS_END__"


def scan_videos(path: str | os.PathLike) -> list[str]:
    """把输入路径展开成视频文件列表：文件直接用；目录递归扫描（排序、仅扩展名匹配）。"""
    p = Path(path)
    if p.is_file():
        return [str(p)]
    if p.is_dir():
        return sorted(str(f) for f in p.rglob("*")
                      if f.is_file() and f.suffix.lower() in VIDEO_EXTS)
    return []


def plan_jobs(inputs: list[str], out_dir: str, out_ext: str) -> list[tuple[str, str]]:
    """按「原名_水印.扩展名」生成 (输入, 输出) 任务列表（输出目录由调用方确保存在）。"""
    out_ext = out_ext.lstrip(".")
    return [(inp, str(Path(out_dir) / f"{Path(inp).stem}_水印.{out_ext}"))
            for inp in inputs]


def _run_one(inp, out, cfg, crf, preset, scale, hw_encoder, hw_codec, hw_decode,
             progress_q=None, idx=0):
    """供进程池调用的顶层函数（必须可 pickle，Windows spawn 要求）。

    progress_q 不为 None 时，把逐帧进度 (文件序号, done, total) 放进队列，
    由父进程的转发线程读出并回调 frame_cb。

    返回 process() 的 stats dict（含 codec），父进程据此在完成消息里
    显示实际编码器（v0.5.7 起）。
    """
    def _cb(done, ftotal):
        try:
            if progress_q is not None:
                progress_q.put((idx, done, ftotal))
        except Exception:  # noqa: BLE001 —— 进度上报失败不影响处理本身
            pass

    return process(inp, out, cfg, crf=crf, preset=preset, scale=scale,
                   hw_encoder=hw_encoder, hw_codec=hw_codec, hw_decode=hw_decode,
                   progress_cb=_cb)


def run_batch(jobs: list[tuple[str, str]], cfg: WatermarkConfig,
              export_params: dict, batch_parallel: int = 0, *,
              progress_q=None, frame_cb=None, file_cb=None,
              cancel_event: threading.Event | None = None) -> dict:
    """批量执行 jobs（[(输入, 输出), ...]），返回
    ``{"total", "ok", "fail", "cancelled"}``（取消跳过的文件不计 ok/fail）。

    - batch_parallel：同时处理的视频数；<=1 或单文件走串行（帧进度直接回调）。
    - export_params：process() 的编码参数 dict（crf/preset/scale/hw_encoder/
      hw_codec/hw_decode）；**不透传 parallel**（帧流水线保持 auto）。
    - frame_cb(idx, done, total)：逐文件帧进度（并行模式由 progress_q 转发线程
      回调，调用线程 ≠ UI 线程，回调方自行调度）。
    - file_cb(idx, msg, ok)：单文件完成（True）/失败（False）消息；取消的文件不回调。
    - cancel_event：置位后串行中断当前文件并停止后续；并行停止提交后续任务。
    """
    total = len(jobs)
    ok = fail = 0
    cancelled = False
    crf = export_params["crf"]
    preset = export_params["preset"]
    scale = export_params["scale"]
    hw_encoder = export_params["hw_encoder"]
    hw_codec = export_params["hw_codec"]
    hw_decode = export_params["hw_decode"]

    if batch_parallel <= 1 or total <= 1:
        # 串行：逐文件处理，帧进度直接回调；取消可中断当前文件
        for idx, (inp, out) in enumerate(jobs):
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break

            def cb(done, ftotal, i=idx):
                if frame_cb is not None:
                    frame_cb(i, done, ftotal)

            try:
                stats = process(inp, out, cfg, crf=crf, preset=preset, scale=scale,
                                hw_encoder=hw_encoder, hw_codec=hw_codec,
                                hw_decode=hw_decode, progress_cb=cb,
                                cancel_event=cancel_event)
                ok += 1
                if file_cb is not None:
                    file_cb(idx, f"完成：{os.path.basename(out)}"
                                 f"（{stats.get('codec', '?')}）", True)
            except ProcessCancelled:
                cancelled = True
                break
            except Exception as exc:  # noqa: BLE001
                fail += 1
                if file_cb is not None:
                    file_cb(idx, f"失败：{os.path.basename(inp)} —— {exc}", False)
        return {"total": total, "ok": ok, "fail": fail, "cancelled": cancelled}

    # 并行：进程池真实并行；有界提交 + 取消后不再提交新任务
    forward = None
    if progress_q is not None:
        def _forward():
            while True:
                item = progress_q.get()
                if item == PROGRESS_END:
                    return
                if frame_cb is not None:
                    idx, done, ftotal = item
                    frame_cb(idx, done, ftotal)

        forward = threading.Thread(target=_forward, daemon=True)
        forward.start()
    try:
        with cf.ProcessPoolExecutor(max_workers=batch_parallel) as pool:
            in_flight: dict = {}
            next_idx = 0
            while True:
                if cancel_event is None or not cancel_event.is_set():
                    while next_idx < total and len(in_flight) < batch_parallel:
                        inp, out = jobs[next_idx]
                        f = pool.submit(_run_one, inp, out, cfg, crf, preset,
                                        scale, hw_encoder, hw_codec, hw_decode,
                                        progress_q, next_idx)
                        in_flight[f] = next_idx
                        next_idx += 1
                if not in_flight:
                    if (cancel_event is not None and cancel_event.is_set()
                            and next_idx < total):
                        cancelled = True
                    break
                done_set, _ = cf.wait(in_flight, return_when=cf.FIRST_COMPLETED)
                for f in done_set:
                    idx = in_flight.pop(f)
                    try:
                        stats = f.result()
                        ok += 1
                        if file_cb is not None:
                            file_cb(idx, f"完成：{os.path.basename(jobs[idx][1])}"
                                         f"（{stats.get('codec', '?')}）", True)
                    except ProcessCancelled:  # 防御：子进程不接收 cancel_event，不应到达
                        cancelled = True
                    except Exception as exc:  # noqa: BLE001
                        fail += 1
                        if file_cb is not None:
                            file_cb(idx, f"失败：{os.path.basename(jobs[idx][0])} —— {exc}", False)
    finally:
        if forward is not None:
            try:
                progress_q.put(PROGRESS_END)
                forward.join(timeout=3)
            except Exception:  # noqa: BLE001
                pass
    return {"total": total, "ok": ok, "fail": fail, "cancelled": cancelled}
