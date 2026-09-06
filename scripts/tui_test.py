"""TUI 专项测试：Textual Pilot 无终端自动化（离屏，CI 可跑）。

运行：  PYTHONIOENCODING=utf-8 .venv/bin/python scripts/tui_test.py
覆盖（随里程碑扩展）：
  1. 应用构建与默认值
  2. 表单填写 → collect_config() 收集正确
  3. 「收集为 JSON」按钮 → config_to_json 输出
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from textual.widgets import Input, Select, Static  # noqa: E402

from app.models import (  # noqa: E402
    KIND_IMAGE, KIND_TEXT, MODE_MOTION, MODE_TILED, config_to_json,
)
from app.tui import WatermarkTuiApp  # noqa: E402

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


async def run_tests() -> None:
    app = WatermarkTuiApp()
    async with app.run_test(size=(100, 40)) as pilot:
        print("== 1. 应用构建与默认值 ==")
        check("应用标题正确", app.TITLE == "视频水印工具 · TUI")
        check("默认模式为平铺", app.query_one("#mode", Select).value == MODE_TILED)
        check("默认来源为文字", app.query_one("#kind", Select).value == KIND_TEXT)

        print("== 2. 表单收集 ==")
        app.query_one("#input_path", Input).value = "in.mp4"
        app.query_one("#output_path", Input).value = "out.mp4"
        app.query_one("#text", Input).value = "机密文件"
        app.query_one("#mode", Select).value = MODE_MOTION
        app.query_one("#kind", Select).value = KIND_TEXT
        await pilot.pause()
        cfg = app.collect_config()
        check("收集 mode=移动", cfg.mode == MODE_MOTION)
        check("收集 kind=文字", cfg.kind == KIND_TEXT)
        check("收集 text", cfg.text == "机密文件")
        check("未填字段取默认值", abs(cfg.angle - 30.0) < 1e-6)  # dataclass 默认

        print("== 3. 收集为 JSON ==")
        await pilot.click("#collect")
        await pilot.pause(0.5)  # 按钮按压动画周期需较长 pause，短 pause 会丢消息
        j = app.last_json
        check("按钮触发 JSON 生成", bool(j))
        check("JSON 含模式与文字", '"mode"' in j and '"text"' in j)
        check("JSON 输出为合法序列化", '"angle"' in j)

        # 恢复后再点一次（验证可重复收集）
        app.query_one("#mode", Select).value = MODE_TILED
        await pilot.pause()
        await pilot.click("#collect")
        await pilot.pause(0.5)
        check("重复收集一致", '"mode": "tiled"' in app.last_json,
              [l.strip() for l in app.last_json.splitlines() if "mode" in l][:1])


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
