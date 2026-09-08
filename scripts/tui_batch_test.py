"""TUI 批量处理专项测试（v0.5.6）：core 层 + Pilot 端到端（串行/并行/取消）。

运行：  PYTHONIOENCODING=utf-8 .venv/bin/python scripts/tui_batch_test.py
覆盖：
  1. core 层：scan_videos（文件/目录递归/排序）与 plan_jobs 命名
  2. core 层：run_batch 取消语义（串行预置位取消 / 并行预置位取消不提交）
  3. TUI 端到端（串行 parallel=1）：3 文件批量 → 产物/日志/进度条
  4. TUI 端到端（并行 parallel=2）：Manager 队列帧进度回传 → 产物/帧进度
  5. TUI 取消路径：Esc → 状态显示已取消、按钮解锁、可再次 Esc 返回
  6. 布局回归：批量屏底部按钮在滚动视口内可达（同 tui_test 第 9 节思路）

注意：并行批量用进程池（Windows spawn / Linux forkserver），
被池子进程导入的 app.core.batch 顶层无重活；本脚本自身带 __main__ 保护。
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from textual.widgets import Button, Input, ListView, ProgressBar, Select, Static  # noqa: E402

from app.core.batch import plan_jobs, run_batch, scan_videos  # noqa: E402
from app.core.encoder import generate_sample_video  # noqa: E402
from app.models import KIND_TEXT, MODE_TILED, WatermarkConfig  # noqa: E402
from app.tui import BatchScreen, WatermarkTuiApp  # noqa: E402

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


def make_cfg() -> WatermarkConfig:
    return WatermarkConfig(kind=KIND_TEXT, mode=MODE_TILED, text="批量测试",
                           font_size=24, angle=30)


EXPORT = {"crf": 23, "preset": "veryfast", "scale": 1.0,
          "hw_encoder": "none", "hw_codec": "h264", "hw_decode": False}


# --------------------------------------------------------------------------
# 1. core 层
# --------------------------------------------------------------------------
def test_core(tmp: Path) -> None:
    print("== 1. core 层：scan_videos / plan_jobs ==")
    d = tmp / "videos"
    (d / "sub").mkdir(parents=True)
    for name in ("b.mp4", "a.mp4", "note.txt", "c.MKV"):
        (d / name).write_bytes(b"x")
    (d / "sub" / "d.mp4").write_bytes(b"x")

    got = scan_videos(str(d))
    check("目录递归扫描+排序+过滤扩展名",
          [Path(p).name for p in got] == ["a.mp4", "b.mp4", "c.MKV", "d.mp4"],
          str([Path(p).name for p in got]))
    single = scan_videos(str(d / "b.mp4"))
    check("单文件直通", single == [str(d / "b.mp4")])
    check("不存在路径返回空", scan_videos(str(tmp / "nope")) == [])

    jobs = plan_jobs([str(d / "a.mp4"), str(d / "b.mp4")], str(tmp / "out"),
                     "mp4")
    check("命名规则 原名_水印.扩展名",
          [Path(o).name for _, o in jobs] == ["a_水印.mp4", "b_水印.mp4"],
          str(jobs))


# --------------------------------------------------------------------------
# 2. core 层取消语义（确定性：预置位 cancel_event）
# --------------------------------------------------------------------------
def test_core_cancel(tmp: Path) -> None:
    print("== 2. core 层：run_batch 取消语义 ==")
    src = tmp / "cancel_src.mp4"
    generate_sample_video(str(src), size=(160, 90), duration=0.6, fps=24,
                          with_audio=False)
    jobs = plan_jobs([str(src)] * 2, str(tmp / "cancel_out"), "mp4")
    (tmp / "cancel_out").mkdir()

    ev = threading.Event()
    ev.set()  # 预置位：第 0 个文件开始前即取消
    res = run_batch(jobs, make_cfg(), EXPORT, 1, cancel_event=ev)
    check("串行预置位取消：cancelled=True", res["cancelled"] is True, str(res))
    check("串行预置位取消：无文件处理", res["ok"] == 0 and res["fail"] == 0)

    ev2 = threading.Event()
    ev2.set()
    res2 = run_batch(jobs, make_cfg(), EXPORT, 2, cancel_event=ev2)
    check("并行预置位取消：不提交任务", res2["cancelled"] and res2["ok"] == 0,
          str(res2))


# --------------------------------------------------------------------------
# Pilot 辅助
# --------------------------------------------------------------------------
async def wait_screen_type(app, screen_cls, timeout_s: float) -> bool:
    for _ in range(int(timeout_s / 0.1)):
        if isinstance(app.screen, screen_cls):
            return True
        await asyncio.sleep(0.1)
    return False


async def add_and_run(pilot, app: WatermarkTuiApp, inputs: list[str],
                      outdir: Path, parallel: str) -> None:
    """打开批量屏、加入文件、设置输出目录与并行数、开始。"""
    app.query_one("#hw_encoder", Select).value = "none"   # 纯 CPU，结果确定
    app.query_one("#preset", Select).value = "veryfast"
    await pilot.pause()
    await pilot.press("f8")
    assert isinstance(app.screen, BatchScreen), "F8 未打开批量屏"
    add_btn = app.screen.query_one("#batch_add", Button)
    add_btn.scroll_visible(animate=False)
    await pilot.pause(0.2)
    for i, inp in enumerate(inputs):
        app.screen.query_one("#batch_input", Input).value = inp
        await pilot.pause(0.2)
        await pilot.click("#batch_add")
        await pilot.pause(0.2)
    app.screen.query_one("#batch_outdir", Input).value = str(outdir)
    app.screen.query_one("#batch_parallel", Input).value = parallel
    await pilot.pause(0.2)
    run_btn = app.screen.query_one("#batch_run", Button)
    run_btn.scroll_visible(animate=False)
    await pilot.pause(0.2)
    await pilot.click("#batch_run")
    await pilot.pause(0.2)


async def wait_batch_done(app: WatermarkTuiApp, timeout_s: float = 240.0):
    """等待批量结束（_batch_active 复位或批量屏已不在栈顶），返回 (状态文本, 日志文本)。"""
    for _ in range(int(timeout_s / 0.2)):
        try:
            if not app.screen._batch_active:
                break
        except Exception:  # noqa: BLE001 —— 屏已弹出/栈空
            break
        await asyncio.sleep(0.2)
    await asyncio.sleep(0.5)  # 等 UI 回调落盘
    status = str(app.screen.query_one("#batch_status", Static).render())
    log = app.screen.query_one("#batch_log")
    log_text = "\n".join(str(line) for line in log.lines)
    return status, log_text


# --------------------------------------------------------------------------
# 3/4. TUI 端到端（串行 / 并行）
# --------------------------------------------------------------------------
async def test_e2e(tmp: Path) -> None:
    print("== 3. TUI 端到端：串行 parallel=1 ==")
    app = WatermarkTuiApp()
    async with app.run_test(size=(110, 48)) as pilot:
        srcs = []
        for name in ("a.mp4", "b.mp4", "c.mp4"):
            p = tmp / name
            generate_sample_video(str(p), size=(160, 90), duration=0.6,
                                  fps=24, with_audio=False)
            srcs.append(str(p))
        outdir = tmp / "out_serial"
        await add_and_run(pilot, app, srcs, outdir, "1")
        check("批量屏打开且 3 文件入列",
              isinstance(app.screen, BatchScreen)
              and len(app.screen._paths) == 3
              and len(app.screen.query_one("#batch_list", ListView).children) == 3)
        status, log_text = await wait_batch_done(app)
        check("串行批量结束：成功 3 失败 0", "成功 3，失败 0" in status, status)
        check("串行日志含 3 条完成", log_text.count("完成：") == 3, log_text)
        outs = sorted(outdir.glob("*.mp4"))
        check("串行输出 3 个文件", len(outs) == 3, str([o.name for o in outs]))
        check("串行命名规则", all("_水印" in o.name for o in outs))
        check("串行输出有效", all(o.stat().st_size > 1000 for o in outs))
        bar = app.screen.query_one("#batch_bar", ProgressBar)
        check("总进度条 100%", abs(bar.progress - 100.0) < 0.01,
              f"progress={bar.progress}")

    print("== 4. TUI 端到端：并行 parallel=2（Manager 队列帧进度） ==")
    app2 = WatermarkTuiApp()
    async with app2.run_test(size=(110, 48)) as pilot:
        outdir = tmp / "out_parallel"
        srcs2 = [str(tmp / n) for n in ("a.mp4", "b.mp4", "c.mp4")]
        await add_and_run(pilot, app2, srcs2, outdir, "2")
        check("并行模式创建 Manager 队列",
              app2.screen._progress_q is not None)
        status, log_text = await wait_batch_done(app2)
        check("并行批量结束：成功 3 失败 0", "成功 3，失败 0" in status, status)
        outs = sorted(outdir.glob("*.mp4"))
        check("并行输出 3 个文件", len(outs) == 3, str([o.name for o in outs]))
        check("并行输出有效", all(o.stat().st_size > 1000 for o in outs))
        # 帧进度经 Manager 队列回传的间接证据：日志/产物齐全 + 状态行收尾更新
        frame_status = str(app2.screen.query_one(
            "#batch_frame_status", Static).render())
        check("帧状态行收尾为已完成", "已完成" in frame_status, frame_status)
        check("Manager 已关停", app2.screen._progress_mgr is None)


# --------------------------------------------------------------------------
# 5. TUI 取消路径 + 6. 布局回归
# --------------------------------------------------------------------------
async def test_cancel_and_layout(tmp: Path) -> None:
    print("== 5. TUI 取消路径 ==")
    app = WatermarkTuiApp()
    async with app.run_test(size=(110, 48)) as pilot:
        # 较长样片：确保取消必然落在文件处理中（而非已跑完走"空闲返回"分支）
        big = tmp / "big.mp4"
        generate_sample_video(str(big), size=(960, 540), duration=20.0,
                              fps=24, with_audio=False)
        outdir = tmp / "out_cancel"
        app.query_one("#hw_encoder", Select).value = "none"
        app.query_one("#preset", Select).value = "veryfast"
        await pilot.pause()
        await pilot.press("f8")
        await add_and_run(pilot, app, [str(big)], outdir, "1")
        # 等首帧进度回调送达（确定处于文件处理中），再取消
        started = False
        for _ in range(300):
            if app.screen._frame_last:
                started = True
                break
            await asyncio.sleep(0.1)
        check("批量进行中", started and app.screen._batch_active is True,
              f"started={started}")
        await pilot.press("escape")  # 运行中 Esc = 取消（不退屏）
        await asyncio.sleep(0.3)
        check("Esc 取消后退屏未发生", isinstance(app.screen, BatchScreen))
        status, _ = await wait_batch_done(app)
        check("状态显示已取消", "已取消" in status, status)
        check("取消后按钮解锁",
              app.screen.query_one("#batch_run", Button).disabled is False)
        await pilot.press("escape")
        await asyncio.sleep(0.3)
        check("空闲 Esc 返回主屏", not isinstance(app.screen, BatchScreen))

    print("== 6. 布局回归：底部按钮可达 ==")
    app3 = WatermarkTuiApp()
    async with app3.run_test(size=(110, 40)) as pilot:
        await pilot.press("f8")
        await pilot.pause(0.3)
        for sel in ("#batch_run", "#batch_cancel"):
            btn = app3.screen.query_one(sel)
            btn.scroll_visible(animate=False)
            await pilot.pause(0.2)
            region = btn.region
            check(f"{sel} 在视口内", region.y >= 0 and region.height > 0,
                  f"region={region}")


async def run_tests() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="vw_tui_batch_"))
    try:
        test_core(tmp)
        test_core_cancel(tmp)
        await test_e2e(tmp)
        await test_cancel_and_layout(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    asyncio.run(run_tests())
    print()
    if failures:
        print(f"失败 {len(failures)} 项: {failures}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
