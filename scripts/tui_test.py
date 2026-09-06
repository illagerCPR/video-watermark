"""TUI 专项测试：Textual Pilot 无终端自动化（离屏，CI 可跑）。

运行：  PYTHONIOENCODING=utf-8 .venv/bin/python scripts/tui_test.py
覆盖：
  1. 应用构建与默认值
  2. fill_from_config → collect_config 全字段往返一致
  3. 导出参数收集
  4. 非法值校验（非整数 / 超范围 / 颜色格式）
  5. --config 预载 + 配置文件保存（JSON 往返）
  6. 「预览 JSON」按钮
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from textual.widgets import Checkbox, Input, Select, Static  # noqa: E402

from app.models import (  # noqa: E402
    KIND_TEXT, MODE_MOTION, MODE_TILED, TRAJECTORY_CIRCLE,
    WatermarkConfig, config_to_json, json_to_config,
)
from app.tui import ConfigError, WatermarkTuiApp  # noqa: E402

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


def sample_cfg() -> WatermarkConfig:
    """覆盖全部字段的有代表性配置。"""
    return WatermarkConfig(
        kind=KIND_TEXT, text="机密文件\n第二行", image_path="logo.png",
        font_name="", font_size=32, text_color=(0, 0, 0), text_opacity=100,
        stroke_width=2, stroke_color=(255, 0, 0),
        img_scale=0.4, img_opacity=111, img_radius=8,
        mode=MODE_MOTION, angle=-45.5, tile_dx=100, tile_dy=50,
        offset_x=3, offset_y=-4, trajectory=TRAJECTORY_CIRCLE,
        speed=2.5, motion_scale=0.35, motion_opacity=150, motion_rotate=True,
        start_sec=1.5, end_sec=8.0,
    )


async def run_tests() -> None:
    # ---------- 1. 构建与默认值 ----------
    app = WatermarkTuiApp()
    async with app.run_test(size=(110, 48)) as pilot:
        print("== 1. 应用构建与默认值 ==")
        check("默认模式为平铺", app.query_one("#mode", Select).value == MODE_TILED)
        check("默认来源为文字", app.query_one("#kind", Select).value == KIND_TEXT)
        check("字号默认 48", app.query_one("#font_size", Input).value == "48")
        check("轨迹默认水平",
              app.query_one("#trajectory", Select).value == "horizontal")

        # ---------- 2. 全字段往返 ----------
        print("== 2. fill_from_config → collect_config 往返 ==")
        cfg = sample_cfg()
        app.fill_from_config(cfg)
        got = app.collect_config()
        check("全字段往返一致", asdict(got) == asdict(cfg))
        if asdict(got) != asdict(cfg):
            for k in asdict(cfg):
                if asdict(got)[k] != asdict(cfg)[k]:
                    print(f"    差异字段 {k}: {asdict(got)[k]!r} != {asdict(cfg)[k]!r}")

        # ---------- 3. 导出参数 ----------
        print("== 3. collect_export_params ==")
        params = app.collect_export_params()
        check("导出参数默认值", params == {
            "crf": 23, "preset": "medium", "scale": 1.0,
            "hw_encoder": "auto", "hw_codec": "h264",
            "hw_decode": True, "parallel": 0}, str(params))
        app.query_one("#crf", Input).value = "20"
        app.query_one("#scale", Input).value = "0.5"
        app.query_one("#parallel", Input).value = "4"
        params = app.collect_export_params()
        check("导出参数收集", params["crf"] == 20 and params["scale"] == 0.5
              and params["parallel"] == 4, str(params))

        # ---------- 4. 非法值校验 ----------
        print("== 4. 非法值校验 ==")
        for wid, bad, expect in (
            ("font_size", "abc", "整数"),
            ("angle", "200", "180"),
            ("text_color", "999,0,0", "0~255"),
            ("text_color", "255,0", "R,G,B"),
            ("end_sec", "abc", "数字或留空"),
        ):
            app.fill_from_config(sample_cfg())
            app.query_one(f"#{wid}", Input).value = bad
            try:
                app.collect_config()
                check(f"非法值 {wid}={bad!r} 报错", False, "未抛 ConfigError")
            except ConfigError as exc:
                check(f"非法值 {wid}={bad!r} 报错", expect in str(exc), str(exc)[:40])

        # ---------- 5. 配置文件预载 + 保存 ----------
        print("== 5. 配置文件预载 + 保存 ==")
        tmp = Path(tempfile.mkdtemp())
        cfg_path = tmp / "cfg.json"
        cfg_path.write_text(config_to_json(sample_cfg()), encoding="utf-8")
        app2 = WatermarkTuiApp(config_path=str(cfg_path))
        async with app2.run_test(size=(110, 48)):
            got = app2.collect_config()
            check("--config 预载往返一致", asdict(got) == asdict(sample_cfg()))
            app2.query_one("#config_path", Input).value = str(tmp / "saved.json")
            app2._save_config()
            saved = Path(tmp / "saved.json").read_text(encoding="utf-8")
            check("保存后 JSON 往返一致",
                  asdict(json_to_config(saved)) == asdict(sample_cfg()))

    # ---------- 6. 预览 JSON 按钮（新实例，避免上段状态干扰） ----------
    from textual.widgets import Button
    app3 = WatermarkTuiApp()
    async with app3.run_test(size=(110, 48)) as pilot:
        print("== 6. 预览 JSON 按钮 ==")
        btn = app3.query_one("#preview_json", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause(0.3)
        await pilot.click("#preview_json")
        await pilot.pause(0.5)
        check("按钮触发 JSON 生成", bool(app3.last_json))
        check("JSON 含 mode/angle", '"mode": "tiled"' in app3.last_json
              and '"angle": 30.0' in app3.last_json)
        # 非法值时按钮不生成 JSON 而是提示
        app3.last_json = ""
        app3.query_one("#font_size", Input).value = "abc"
        btn.scroll_visible(animate=False)
        await pilot.pause(0.3)
        await pilot.click("#preview_json")
        await pilot.pause(0.5)
        check("非法值时按钮不生成", app3.last_json == "")


    # ---------- 7. 预览（帧 + 轨迹，需样片） ----------
    from textual.widgets import Button
    from app.tui import PreviewScreen
    sample = ROOT / "outputs" / "sample_video.mp4"
    if not sample.is_file():
        print("== 7. 预览：跳过（缺 outputs/sample_video.mp4，先跑 step1_demo.py）==")
    else:
        print("== 7. 预览（半块像素：帧 + 轨迹） ==")
        app4 = WatermarkTuiApp(config_path=str(cfg_path))
        async with app4.run_test(size=(110, 48)) as pilot:
            app4.query_one("#input_path", Input).value = str(sample)
            await pilot.pause()

            async def wait_screen(app, timeout_s=15.0):
                for _ in range(int(timeout_s / 0.1)):
                    if isinstance(app.screen, PreviewScreen):
                        return True
                    await pilot.pause(0.1)
                return False

            async def wait_preview_ready(app, want_sketch: bool,
                                         timeout_s=15.0) -> bool:
                """等待 PreviewScreen 出现且其子组件 compose 完成。"""
                for _ in range(int(timeout_s / 0.1)):
                    if isinstance(app.screen, PreviewScreen):
                        try:
                            fr = app.screen.query_one("#preview_frame", Static)
                            if fr.render() is None:
                                continue
                            if want_sketch:
                                sk = app.screen.query_one("#preview_sketch",
                                                          Static)
                                if len(str(sk.render())) <= 20:
                                    continue
                            return True
                        except Exception:  # noqa: BLE001  compose 未完成
                            pass
                    await asyncio.sleep(0.1)
                return False

            async def click_scrolled(sel: str):
                app4.query_one(sel, Button).scroll_visible(animate=False)
                await pilot.pause(0.3)
                await pilot.click(sel)

            # F6 = 仅轨迹示意（无轨迹区；验证屏幕打开 + 帧渲染）
            await pilot.press("f6")
            if await wait_preview_ready(app4, want_sketch=False):
                check("轨迹示意预览屏打开", True)
                check("帧渲染非空",
                      len(str(app4.screen.query_one("#preview_frame", Static).render())) > 100)
                await pilot.press("escape")
                await pilot.pause(0.5)
                check("ESC 返回主屏", not isinstance(app4.screen, PreviewScreen))
            else:
                check("轨迹示意预览屏打开", False, "15s 内未打开")

            # F5 = 帧 + 轨迹
            await pilot.press("f5")
            if await wait_preview_ready(app4, want_sketch=True):
                check("帧+轨迹预览屏打开", True)
                st = app4.screen.query_one("#preview_sketch", Static)
                check("轨迹渲染非空", len(str(st.render())) > 20)
                check("帧渲染非空",
                      len(str(app4.screen.query_one("#preview_frame", Static).render())) > 100)
            else:
                check("帧+轨迹预览屏打开", False, "15s 内未打开")


    # ---------- 8. 导出（engine 取消 + TUI 端到端） ----------
    import threading as _th
    from app.core.encoder import (  # noqa: E402
        ProcessCancelled as _PC, generate_sample_video, process as _process,
    )
    from app.tui import ExportScreen  # noqa: E402

    print("== 8. 导出（取消 + 端到端） ==")
    tmp2 = Path(tempfile.mkdtemp())
    src8 = tmp2 / "src8.mp4"
    generate_sample_video(str(src8), size=(320, 180), duration=2.0, fps=30)

    # 8a. engine 级确定性取消（预置位 event → 第 0 帧即中断）
    ev = _th.Event()
    ev.set()
    try:
        _process(str(src8), str(tmp2 / "x.mp4"), WatermarkConfig(text="T"),
                 hw_encoder="none", hw_decode=False, cancel_event=ev)
        check("engine 预置位取消", False, "未抛 ProcessCancelled")
    except _PC:
        check("engine 预置位取消（无 tmp 残留）",
              not list(tmp2.glob(".vw_tmp_*")))

    # 8b. TUI 端到端导出（F7 → ExportScreen → 完成回调）
    app5 = WatermarkTuiApp()
    out8 = tmp2 / "out8.mp4"
    async with app5.run_test(size=(110, 48)) as pilot:
        app5.query_one("#input_path", Input).value = str(src8)
        app5.query_one("#output_path", Input).value = str(out8)
        app5.query_one("#hw_encoder", Select).value = "none"
        await pilot.pause()
        await pilot.press("f7")
        if not await wait_screen_type(app5, ExportScreen, 10.0):
            check("导出屏打开", False, "10s 内未打开")
        else:
            check("导出屏打开", True)
            ok = False
            for _ in range(1200):  # 最多 120s
                st_text = str(app5.screen.query_one(
                    "#export_status", Static).render())
                if "完成" in st_text or "失败" in st_text:
                    ok = "完成" in st_text
                    break
                await pilot.pause(0.1)
            check("端到端导出完成", ok)
            check("输出文件有效", out8.is_file() and out8.stat().st_size > 1000)

    # ---------- 9. 布局回归（v0.5.1：行内溢出 / 底部按钮可达 / resize） ----------
    from textual.containers import Horizontal  # noqa: E402

    print("== 9. 布局回归（行内溢出 / 底部按钮） ==")
    app6 = WatermarkTuiApp()

    async def check_form_layout(tag: str) -> None:
        form = app6.query_one("#form")
        check(f"[{tag}] #form 无横向溢出", form.max_scroll_x == 0)
        over = []
        for row in form.query(Horizontal):
            over += [c for c in row.children
                     if c.region.right > row.region.right]
        check(f"[{tag}] 行内子件不越界", not over,
              str([(type(c).__name__, c.id) for c in over]))
        form.scroll_to(y=form.max_scroll_y, animate=False)
        await pilot6.pause(0.15)
        text = "\n".join(s.text
                         for s in app6.screen._compositor.render_strips())
        check(f"[{tag}] 滚到底可见底部按钮", "加载配置" in text)

    async with app6.run_test(size=(171, 43)) as pilot6:
        await pilot6.pause(0.2)
        await check_form_layout("171x43")
        await pilot6.resize_terminal(120, 30)
        await pilot6.pause(0.3)
        await check_form_layout("120x30")
        await pilot6.resize_terminal(90, 26)
        await pilot6.pause(0.3)
        await check_form_layout("90x26")

    # ---------- 10. 硬件检测按钮（v0.5.4：与 GUI「检测」同源） ----------
    print("== 10. 硬件检测按钮 ==")
    app7 = WatermarkTuiApp()
    async with app7.run_test(size=(110, 40)) as pilot7:
        btn = app7.query_one("#hw_detect", Button)
        btn.scroll_visible(animate=False)
        await pilot7.pause(0.5)
        await pilot7.click(btn)
        await pilot7.pause(0.5)
        ok = False
        for _ in range(400):  # 最多 40s：候选编码器需逐个实测编码
            txt = str(app7._hw_info.render())
            if "硬件解码器" in txt or "检测失败" in txt:
                ok = "硬件解码器" in txt
                break
            await pilot7.pause(0.1)
        check("检测输出含编码器+解码器报告", ok, txt[:60])
        check("检测输出附当前二进制", "当前 ffmpeg" in txt)

    # ---------- 11. 导出屏编码器/解码显示（v0.5.4） ----------
    print("== 11. 导出屏编码器显示 ==")
    app8 = WatermarkTuiApp()
    tmp3 = Path(tempfile.mkdtemp())
    src11 = tmp3 / "src11.mp4"
    generate_sample_video(str(src11), size=(160, 90), duration=0.4, fps=10)
    async with app8.run_test(size=(110, 40)) as pilot8:
        app8.query_one("#input_path", Input).value = str(src11)
        app8.query_one("#hw_encoder", Select).value = "none"
        await pilot8.pause()
        await pilot8.press("f7")
        if not await wait_screen_type(app8, ExportScreen, 10.0):
            check("导出屏打开", False, "10s 内未打开")
        else:
            meta = str(app8.screen.query_one("#export_meta", Static).render())
            check("导出屏显示编码器", "编码器" in meta, meta)
    shutil.rmtree(tmp3, ignore_errors=True)


async def wait_screen_type(app, screen_cls, timeout_s: float) -> bool:
    for _ in range(int(timeout_s / 0.1)):
        if isinstance(app.screen, screen_cls):
            return True
        await asyncio.sleep(0.1)
    return False


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
