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

            async def click_scrolled(sel: str):
                app4.query_one(sel, Button).scroll_visible(animate=False)
                await pilot.pause(0.3)
                await pilot.click(sel)

            # F6 = 仅轨迹示意（无轨迹区；验证屏幕打开 + 帧渲染）
            await pilot.press("f6")
            if await wait_screen(app4):
                check("轨迹示意预览屏打开", True)
                check("帧渲染非空",
                      len(str(app4.screen.query_one("#preview_frame", Static).render())) > 100)
                await pilot.press("escape")
                await pilot.pause(0.3)
                check("ESC 返回主屏", not isinstance(app4.screen, PreviewScreen))
            else:
                check("轨迹示意预览屏打开", False, "15s 内未打开")

            # F5 = 帧 + 轨迹
            await pilot.press("f5")
            if await wait_screen(app4):
                check("帧+轨迹预览屏打开", True)
                st = app4.screen.query_one("#preview_sketch", Static)
                check("轨迹渲染非空", len(str(st.render())) > 20)
                check("帧渲染非空",
                      len(str(app4.screen.query_one("#preview_frame", Static).render())) > 100)
            else:
                check("帧+轨迹预览屏打开", False, "15s 内未打开")


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
