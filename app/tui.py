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

import json
import sys
import threading
import time as _time
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult, ScreenStackError
from textual.screen import ModalScreen
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Footer, Header, Input, ProgressBar, Select, Static, TextArea

from . import __version__
from .core.encoder import ProcessCancelled, process
from .models import (
    KIND_IMAGE, KIND_TEXT, MODE_MOTION, MODE_TILED,
    TRAJECTORIES, TRAJECTORY_LABELS,
    WatermarkConfig, config_to_json, json_to_config,
)

# Select 的 options 为 (label, value) 元组
MODE_CHOICES = [("平铺水印", MODE_TILED), ("移动水印", MODE_MOTION)]
KIND_CHOICES = [("文字水印", KIND_TEXT), ("图片水印", KIND_IMAGE)]
TRAJ_CHOICES = [(TRAJECTORY_LABELS[t], t) for t in TRAJECTORIES]
HW_ENCODER_CHOICES = [
    ("自动（推荐）", "auto"), ("关闭（纯 CPU）", "none"),
    ("NVIDIA NVENC", "nvenc"), ("Intel QSV", "qsv"), ("AMD AMF", "amf"),
    ("Microsoft D3D12VA", "d3d12va"), ("MediaFoundation", "mf"),
]
HW_CODEC_CHOICES = [("H.264", "h264"), ("HEVC (H.265)", "hevc")]
PRESET_CHOICES = [(p, p) for p in (
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow",
)]


class ConfigError(ValueError):
    """表单值不合法（collect_config 抛出，GUI 侧转提示）。"""


class PreviewScreen(ModalScreen):
    """预览屏：合成水印后的视频帧 + 轨迹示意（半块像素渲染）。"""

    BINDINGS = [("escape", "app.pop_screen", "返回"), ("f5", "app.pop_screen", "返回")]

    def __init__(self, frame_text, sketch_text) -> None:
        super().__init__()
        self._frame_text = frame_text
        self._sketch_text = sketch_text

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="preview_body"):
            yield Static("视频帧预览（含水印）", classes="section")
            yield Static(self._frame_text, id="preview_frame")
            if self._sketch_text is not None:
                yield Static("移动轨迹示意", classes="section")
                yield Static(self._sketch_text, id="preview_sketch")
        yield Footer()

    def update_content(self, frame_text, sketch_text) -> None:
        self.query_one("#preview_frame", Static).update(frame_text)
        if sketch_text is not None:
            self.query_one("#preview_sketch", Static).update(sketch_text)


class ExportScreen(ModalScreen):
    """导出进度屏：帧进度 + 平滑速率 + ETA + 取消。"""

    BINDINGS = [("escape", "cancel_or_close", "取消/关闭")]

    def __init__(self, total: int) -> None:
        super().__init__()
        self._total = max(1, total)

    def compose(self) -> ComposeResult:
        with Vertical(id="export_body"):
            yield Static("准备中…", id="export_status")
            yield ProgressBar(total=100.0, show_eta=False, id="export_bar")
            with Horizontal():
                yield Button("取消导出", id="export_cancel", variant="error")
                yield Button("关闭", id="export_close", disabled=True)
        yield Footer()

    def update_progress(self, done: int, total: int, status: str) -> None:
        self.query_one("#export_bar", ProgressBar).update(
            progress=done / self._total * 100)
        if status:
            self.query_one("#export_status", Static).update(status)

    def mark_finished(self, msg: str) -> None:
        self.query_one("#export_status", Static).update(msg)
        self.query_one("#export_bar", ProgressBar).update(progress=100.0)
        self.query_one("#export_cancel", Button).disabled = True
        self.query_one("#export_close", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "export_cancel":
            self.app._cancel_export()
        elif event.button.id == "export_close":
            self.app.pop_screen()

    def action_cancel_or_close(self) -> None:
        if self.query_one("#export_close", Button).disabled:
            self.app._cancel_export()
        else:
            self.app.pop_screen()


class WatermarkTuiApp(App[None]):
    """视频水印 TUI 主应用。"""

    TITLE = "视频水印工具 · TUI"
    SUB_TITLE = f"v{__version__}"  # 单一来源：app/__init__.py

    CSS = """
    #form { height: 1fr; padding: 0 1; } /* 1fr=滚动视口：长表单内部滚动，勿改 auto（会溢出屏幕） */
    /* 滚动容器里 Horizontal 的 1fr 高会塌成 1 行（按钮 3 行画不下→滚到底也看不到最后一行），
       Input 默认 width:100% 会把同行按钮挤出 overflow:hidden 的行外 → 显式改为 auto/1fr */
    #form Horizontal { height: auto; }
    #form Horizontal Input { width: 1fr; }
    .section { color: $text-muted; text-style: bold; margin-top: 1; }
    Input, Select { margin-bottom: 0; }
    TextArea { height: 5; margin-bottom: 0; }
    #actions { height: auto; padding: 1 1; }
    #json_out {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
        color: $text-muted;
    }
    PreviewScreen #preview_body { height: 1fr; }
    PreviewScreen Static { margin-bottom: 0; }
    ExportScreen #export_body { height: auto; padding: 1 2; }
    ExportScreen ProgressBar { margin-bottom: 1; }
    """

    BINDINGS = [("ctrl+q", "quit", "退出"), ("ctrl+s", "save_config", "保存配置"),
                ("f5", "preview_frame", "预览帧"),
                ("f6", "preview_sketch", "轨迹示意"),
                ("f7", "export_run", "开始导出")]

    def __init__(self, config_path: str | None = None) -> None:
        super().__init__()
        self.config_path_arg = config_path  # 启动时 --config 预载
        self.last_json: str = ""  # 最近一次「预览 JSON」的结果（测试断言用）
        self._cancel_event: threading.Event | None = None
        self._export_t0: float = 0.0
        self._last_ui_update: float = 0.0

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="form"):
            yield Static("视频文件", classes="section")
            yield Input(placeholder="输入视频路径", id="input_path")
            yield Input(placeholder="输出视频路径（留空自动命名）", id="output_path")

            yield Static("水印来源", classes="section")
            yield Select(KIND_CHOICES, value=KIND_TEXT, id="kind", allow_blank=False)
            yield TextArea(placeholder="文字内容（支持多行）", id="text")
            yield Input(placeholder="图片水印路径（来源=图片时使用）", id="image_path")

            yield Static("文字样式", classes="section")
            yield Input(placeholder="字体（空 = 自动选系统中文字体）", id="font_name")
            yield Input(value="48", id="font_size")
            yield Input(value="255,255,255", id="text_color")
            yield Input(value="90", id="text_opacity")
            yield Input(value="0", id="stroke_width")
            yield Input(value="0,0,0", id="stroke_color")

            yield Static("图片样式", classes="section")
            yield Input(value="0.3", id="img_scale")
            yield Input(value="128", id="img_opacity")
            yield Input(value="0", id="img_radius")

            yield Static("模式", classes="section")
            yield Select(MODE_CHOICES, value=MODE_TILED, id="mode", allow_blank=False)

            yield Static("平铺参数", classes="section")
            yield Input(value="30.0", id="angle")
            yield Input(value="260", id="tile_dx")
            yield Input(value="160", id="tile_dy")
            yield Input(value="0", id="offset_x")
            yield Input(value="0", id="offset_y")

            yield Static("移动参数", classes="section")
            yield Select(TRAJ_CHOICES, id="trajectory", allow_blank=False)
            yield Input(value="1.0", id="speed")
            yield Input(value="0.2", id="motion_scale")
            yield Input(value="200", id="motion_opacity")
            yield Checkbox("移动水印随时间自转", id="motion_rotate")

            yield Static("出现时间范围（秒，结束留空 = 直到结尾）", classes="section")
            yield Input(value="0.0", id="start_sec")
            yield Input(placeholder="（空 = 直到结尾）", id="end_sec")

            yield Static("预览（需先填输入视频）", classes="section")
            with Horizontal():
                yield Input(value="1.0", id="preview_time")
                yield Button("预览帧 (F5)", id="preview_frame")
                yield Button("轨迹示意 (F6)", id="preview_sketch")

            yield Static("输出与编码", classes="section")
            yield Input(value="23", id="crf")
            yield Select(PRESET_CHOICES, value="medium", id="preset", allow_blank=False)
            yield Input(value="1.0", id="scale")
            yield Select(HW_ENCODER_CHOICES, value="auto", id="hw_encoder",
                         allow_blank=False)
            yield Select(HW_CODEC_CHOICES, value="h264", id="hw_codec",
                         allow_blank=False)
            yield Checkbox("启用硬件解码（失败自动回退）", id="hw_decode", value=True)
            yield Input(value="0", id="parallel")

            yield Static("配置文件", classes="section")
            yield Input(placeholder="配置 JSON 路径", id="config_path")
            with Horizontal():
                yield Button("加载配置", id="load_config")
                yield Button("保存配置", id="save_config", variant="primary")

        with Horizontal(id="actions"):
            yield Button("预览 JSON", id="preview_json")
            yield Button("开始导出 (F7)", id="export_run", variant="success")
        yield Static("（尚未生成）", id="json_out")
        yield Footer()

    def on_mount(self) -> None:
        if self.config_path_arg:
            self.query_one("#config_path", Input).value = self.config_path_arg
            self._load_config()

    # ------------------------------------------------------------------
    # 取值辅助（带校验，错误信息带字段名）
    # ------------------------------------------------------------------
    def _int(self, wid: str, name: str, lo: float | None = None,
             hi: float | None = None) -> int:
        raw = self.query_one(f"#{wid}", Input).value.strip()
        try:
            v = int(raw)
        except ValueError:
            raise ConfigError(f"「{name}」需为整数，当前：{raw!r}") from None
        if lo is not None and v < lo or hi is not None and v > hi:
            raise ConfigError(f"「{name}」需在 {lo}~{hi}，当前：{v}")
        return v

    def _float(self, wid: str, name: str, lo: float | None = None,
               hi: float | None = None) -> float:
        raw = self.query_one(f"#{wid}", Input).value.strip()
        try:
            v = float(raw)
        except ValueError:
            raise ConfigError(f"「{name}」需为数字，当前：{raw!r}") from None
        if lo is not None and v < lo or hi is not None and v > hi:
            raise ConfigError(f"「{name}」需在 {lo}~{hi}，当前：{v}")
        return v

    def _rgb(self, wid: str, name: str) -> tuple:
        raw = self.query_one(f"#{wid}", Input).value.strip()
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) != 3:
            raise ConfigError(f"「{name}」需为 R,G,B 三段（如 255,255,255），当前：{raw!r}")
        try:
            rgb = tuple(int(p) for p in parts)
        except ValueError:
            raise ConfigError(f"「{name}」含非整数分量：{raw!r}") from None
        if any(not (0 <= c <= 255) for c in rgb):
            raise ConfigError(f"「{name}」分量需在 0~255：{raw!r}")
        return rgb

    def _opt_float(self, wid: str, name: str) -> float | None:
        raw = self.query_one(f"#{wid}", Input).value.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            raise ConfigError(f"「{name}」需为数字或留空，当前：{raw!r}") from None

    # ------------------------------------------------------------------
    # 参数收集
    # ------------------------------------------------------------------
    def collect_config(self) -> WatermarkConfig:
        """从表单收集 WatermarkConfig（全字段；不合法抛 ConfigError）。"""
        return WatermarkConfig(
            kind=self.query_one("#kind", Select).value,
            text=self.query_one("#text", TextArea).text,
            image_path=self.query_one("#image_path", Input).value.strip(),
            font_name=self.query_one("#font_name", Input).value.strip(),
            font_size=self._int("font_size", "字号", 1, 500),
            text_color=self._rgb("text_color", "文字颜色"),
            text_opacity=self._int("text_opacity", "文字透明度", 0, 255),
            stroke_width=self._int("stroke_width", "描边宽度", 0, 100),
            stroke_color=self._rgb("stroke_color", "描边颜色"),
            img_scale=self._float("img_scale", "图片缩放比例", 0.01, 10),
            img_opacity=self._int("img_opacity", "图片透明度", 0, 255),
            img_radius=self._int("img_radius", "图片圆角", 0, 500),
            mode=self.query_one("#mode", Select).value,
            angle=self._float("angle", "平铺角度", -180, 180),
            tile_dx=self._int("tile_dx", "横向间距", 1),
            tile_dy=self._int("tile_dy", "纵向间距", 1),
            offset_x=self._int("offset_x", "偏移 X"),
            offset_y=self._int("offset_y", "偏移 Y"),
            trajectory=self.query_one("#trajectory", Select).value,
            speed=self._float("speed", "移动速度", 0.01, 20),
            motion_scale=self._float("motion_scale", "移动水印宽度比例", 0.01, 10),
            motion_opacity=self._int("motion_opacity", "移动水印透明度", 0, 255),
            motion_rotate=self.query_one("#motion_rotate", Checkbox).value,
            start_sec=self._float("start_sec", "开始时间", 0),
            end_sec=self._opt_float("end_sec", "结束时间"),
        )

    def collect_export_params(self) -> dict:
        """收集编码/导出参数（process() 的关键字参数，非 WatermarkConfig 字段）。"""
        parallel = self._int("parallel", "并行 worker 数", 0, 64)
        return {
            "crf": self._int("crf", "CRF", 0, 51),
            "preset": self.query_one("#preset", Select).value,
            "scale": self._float("scale", "分辨率缩放", 0.1, 10),
            "hw_encoder": self.query_one("#hw_encoder", Select).value,
            "hw_codec": self.query_one("#hw_codec", Select).value,
            "hw_decode": self.query_one("#hw_decode", Checkbox).value,
            "parallel": parallel,
        }

    def fill_from_config(self, cfg: WatermarkConfig) -> None:
        """用配置回填表单。"""
        def put(wid: str, value):
            w = self.query_one(f"#{wid}")
            if isinstance(w, Input):
                w.value = "" if value is None else str(value)
            elif isinstance(w, TextArea):
                w.text = value
            elif isinstance(w, Checkbox):
                w.value = bool(value)
            elif isinstance(w, Select):
                w.value = value

        put("text", cfg.text)
        put("image_path", cfg.image_path)
        put("font_name", cfg.font_name)
        put("font_size", cfg.font_size)
        put("text_color", ",".join(str(c) for c in cfg.text_color))
        put("text_opacity", cfg.text_opacity)
        put("stroke_width", cfg.stroke_width)
        put("stroke_color", ",".join(str(c) for c in cfg.stroke_color))
        put("img_scale", cfg.img_scale)
        put("img_opacity", cfg.img_opacity)
        put("img_radius", cfg.img_radius)
        put("mode", cfg.mode)
        put("angle", cfg.angle)
        put("tile_dx", cfg.tile_dx)
        put("tile_dy", cfg.tile_dy)
        put("offset_x", cfg.offset_x)
        put("offset_y", cfg.offset_y)
        put("trajectory", cfg.trajectory)
        put("speed", cfg.speed)
        put("motion_scale", cfg.motion_scale)
        put("motion_opacity", cfg.motion_opacity)
        put("motion_rotate", cfg.motion_rotate)
        put("start_sec", cfg.start_sec)
        put("end_sec", cfg.end_sec)

    # ------------------------------------------------------------------
    # 配置文件加载/保存
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        raw_path = self.query_one("#config_path", Input).value.strip()
        if not raw_path:
            self.notify("请先填写配置文件路径", severity="warning")
            return
        try:
            cfg = json_to_config(Path(raw_path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.notify(f"配置文件不存在：{raw_path}", severity="error")
            return
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            self.notify(f"配置解析失败：{exc}", severity="error")
            return
        self.fill_from_config(cfg)
        self.notify("配置已加载", severity="information")

    def _save_config(self) -> None:
        raw_path = self.query_one("#config_path", Input).value.strip()
        if not raw_path:
            self.notify("请先填写配置文件路径", severity="warning")
            return
        try:
            cfg = self.collect_config()
        except ConfigError as exc:
            self.notify(str(exc), severity="error")
            return
        Path(raw_path).write_text(config_to_json(cfg), encoding="utf-8")
        self.notify(f"配置已保存：{raw_path}", severity="information")

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "preview_json":
            try:
                self.last_json = config_to_json(self.collect_config())
                self.query_one("#json_out", Static).update(self.last_json)
            except ConfigError as exc:
                self.notify(str(exc), severity="error")
        elif event.button.id == "load_config":
            self._load_config()
        elif event.button.id == "save_config":
            self._save_config()
        elif event.button.id == "preview_frame":
            self._open_preview()
        elif event.button.id == "preview_sketch":
            self._open_preview(with_sketch=False)
        elif event.button.id == "export_run":
            self._start_export()

    # ------------------------------------------------------------------
    # 导出（M4：后台线程 + 进度/速率/ETA + 取消）
    # ------------------------------------------------------------------
    def _start_export(self) -> None:
        video = self.query_one("#input_path", Input).value.strip()
        if not video or not Path(video).is_file():
            self.notify("请先填写正确的输入视频路径", severity="error")
            return
        try:
            cfg = self.collect_config()
            params = self.collect_export_params()
        except ConfigError as exc:
            self.notify(str(exc), severity="error")
            return
        output = self.query_one("#output_path", Input).value.strip()
        if not output:
            p = Path(video)
            output = str(p.with_name(p.stem + "_watermarked.mp4"))
        if Path(output).resolve() == Path(video).resolve():
            self.notify("输出路径不能与输入相同", severity="error")
            return
        from .core.encoder import probe
        try:
            total = probe(video)["frames"] or 0
        except Exception as exc:  # noqa: BLE001
            self.notify(f"无法读取视频信息：{exc}", severity="error")
            return
        self._cancel_event = threading.Event()
        self.push_screen(ExportScreen(total))
        self._export_worker(video, output, cfg, params, self._cancel_event)

    @work(thread=True, exclusive=True, group="export")
    def _export_worker(self, video: str, output: str, cfg: WatermarkConfig,
                       params: dict, cancel_event: threading.Event) -> None:
        t0 = _time.monotonic()
        self._export_t0 = t0
        self._last_ui_update = 0.0

        def cb(done: int, tot: int) -> None:
            now = _time.monotonic()
            if now - self._last_ui_update < 0.1:  # 节流：每 0.1s 最多刷一次 UI
                return
            self._last_ui_update = now
            elapsed = now - t0
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (tot - done) / rate if rate > 0 and tot else 0.0
            self.call_from_thread(self._export_screen_update,
                                  done, tot, rate, eta)

        try:
            stats = process(video, output, cfg, progress_cb=cb,
                            cancel_event=cancel_event, **params)
        except ProcessCancelled:
            self.call_from_thread(self._export_finished,
                                  "已取消（输出未生成）", None)
            return
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self._export_finished, f"失败：{exc}", None)
            return
        self.call_from_thread(
            self._export_finished,
            f"完成 ✓ {stats['frames']} 帧 · {stats['width']}x{stats['height']}"
            f" · 编码器 {stats['codec']}\n输出：{output}", stats)

    def _export_screen_update(self, done: int, total: int,
                              rate: float, eta: float) -> None:
        try:
            if not isinstance(self.screen, ExportScreen):
                return
            status = (f"第 {done}/{total} 帧 · {rate:.1f} 帧/秒"
                      + (f" · 剩余 ~{eta:.0f} 秒" if eta > 0 else ""))
            self.screen.update_progress(done, total, status)
        except ScreenStackError:
            pass  # app 关闭竞态：栈已空，无需更新

    def _export_finished(self, msg: str, stats) -> None:
        try:
            if isinstance(self.screen, ExportScreen):
                self.screen.mark_finished(msg)
            else:
                self.notify(msg, severity="information")
        except ScreenStackError:
            pass

    def _cancel_export(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.notify("正在取消…", severity="warning")

    # ------------------------------------------------------------------
    # 预览（M3：半块像素渲染，后台线程抽帧避免卡 UI）
    # ------------------------------------------------------------------
    def _open_preview(self, with_sketch: bool = True) -> None:
        video = self.query_one("#input_path", Input).value.strip()
        if not video:
            self.notify("请先填写输入视频路径", severity="warning")
            return
        if not Path(video).is_file():
            self.notify(f"输入视频不存在：{video}", severity="error")
            return
        try:
            cfg = self.collect_config()
            t = self._float("preview_time", "预览时间点", 0)
        except ConfigError as exc:
            self.notify(str(exc), severity="error")
            return
        self._render_preview_worker(video, cfg, t, with_sketch)

    @work(thread=True, exclusive=True, group="preview")
    def _render_preview_worker(self, video: str, cfg: WatermarkConfig,
                               t: float, with_sketch: bool) -> None:
        from . import tui_preview
        try:
            frame_text = tui_preview.image_to_half_blocks(
                tui_preview.grab_composited_frame(video, cfg, t))
            sketch_text = (tui_preview.image_to_half_blocks(
                tui_preview.sketch(cfg), max_rows=25) if with_sketch else None)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self.notify, f"预览失败：{exc}", severity="error")
            return
        self.call_from_thread(self._show_preview_screen, frame_text, sketch_text)

    def _show_preview_screen(self, frame_text, sketch_text) -> None:
        if not isinstance(self.screen, PreviewScreen):
            self.push_screen(PreviewScreen(frame_text, sketch_text))
        else:
            self.screen.update_content(frame_text, sketch_text)

    def action_save_config(self) -> None:
        self._save_config()

    def action_preview_frame(self) -> None:
        self._open_preview()

    def action_preview_sketch(self) -> None:
        self._open_preview(with_sketch=False)

    def action_export_run(self) -> None:
        self._start_export()


def main(argv: list[str] | None = None) -> int:
    """TUI 入口（`python -m app.tui` / `python -m app.cli --tui` 共用）。"""
    import argparse

    p = argparse.ArgumentParser(
        prog="video-watermark-tui", description="视频水印工具（TUI 交互模式）")
    p.add_argument("--config", help="加载 JSON 配置作为初始值")
    args = p.parse_args(argv)

    app = WatermarkTuiApp(config_path=args.config)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
