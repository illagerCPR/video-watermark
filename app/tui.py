"""TUI 交互模式（v0.5.0 起）：Textual 全屏终端界面。

设计原则：TUI 只做「参数收集 + 进度展示」，业务逻辑全部复用——
- 表单字段 ↔ WatermarkConfig（app/models.py，含 JSON 序列化往返）
- 预览/轨迹 → app/core/preview.py（M3）
- 导出/进度/取消 → app/core/encoder.process()（M4）
- ffmpeg 来源 / 硬件探测 → ffbin / hwaccel（状态栏展示）

入口：`python -m app.tui`；或 `python -m app.cli --tui`。
测试：scripts/tui_test.py（Textual Pilot 无终端自动化，CI 可跑）。
"""
from __future__ import annotations

import sys

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Select, Static

from .models import (
    KIND_IMAGE, KIND_TEXT, MODE_MOTION, MODE_TILED,
    WatermarkConfig, config_to_json,
)

# Select 的 options 为 (label, value) 元组
MODE_CHOICES = [
    ("平铺水印", MODE_TILED),
    ("移动水印", MODE_MOTION),
]
KIND_CHOICES = [
    ("文字水印", KIND_TEXT),
    ("图片水印", KIND_IMAGE),
]


class WatermarkTuiApp(App[None]):
    """视频水印 TUI 主应用。"""

    TITLE = "视频水印工具 · TUI"
    SUB_TITLE = "v0.5.0-dev"

    CSS = """
    #form {
        height: auto;
        padding: 0 1;
    }
    .section {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }
    Input, Select {
        margin-bottom: 1;
    }
    #actions {
        height: auto;
        padding: 1 1;
    }
    #json_out {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS = [("ctrl+q", "quit", "退出")]

    def __init__(self) -> None:
        super().__init__()
        self.last_json: str = ""  # 最近一次「收集为 JSON」的结果（测试断言用）

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="form"):
            yield Static("视频文件", classes="section")
            yield Input(placeholder="输入视频路径", id="input_path")
            yield Input(placeholder="输出视频路径（留空自动命名）", id="output_path")
            yield Static("水印", classes="section")
            yield Select(MODE_CHOICES, value=MODE_TILED, id="mode",
                         allow_blank=False)
            yield Select(KIND_CHOICES, value=KIND_TEXT, id="kind",
                         allow_blank=False)
            yield Input(placeholder="文字内容（M2 起支持多行）", id="text")
        with Horizontal(id="actions"):
            yield Button("收集为 JSON", id="collect", variant="primary")
        yield Static("（尚未生成）", id="json_out")
        yield Footer()

    # ------------------------------------------------------------------
    # 参数收集
    # ------------------------------------------------------------------
    def collect_config(self) -> WatermarkConfig:
        """从表单收集 WatermarkConfig。

        M1 仅收集基础字段（mode/kind/text），其余取 dataclass 默认值；
        M2 扩展为全字段收集 + 校验。
        """
        return WatermarkConfig(
            mode=self.query_one("#mode", Select).value,
            kind=self.query_one("#kind", Select).value,
            text=self.query_one("#text", Input).value,
        )

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "collect":
            self.last_json = config_to_json(self.collect_config())
            self.query_one("#json_out", Static).update(self.last_json)


def main(argv: list[str] | None = None) -> int:
    """TUI 入口（`python -m app.tui` / `python -m app.cli --tui` 共用）。"""
    app = WatermarkTuiApp()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
