"""视频水印工具 - 主窗口。

布局：
  左列：参数面板（滚动区）—— 输入/输出、模式、来源、文字/图片、平铺/移动参数、时间范围
  右列：视频信息 + 预览（单帧水印效果 / 轨迹示意图）+ 导出进度
"""
from __future__ import annotations

import os
import sys
import time
from collections import deque

from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSlider, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from ..core import ffbin
from ..core import preview
from ..core.encoder import probe, process
from ..core.hwaccel import describe_available, detect_encoders
from ..core.subproc import popen as popen_hidden  # 隐藏窗口启动 explorer（避免闪命令窗）
from ..core.watermark import list_available_fonts
from ..models import (
    KIND_IMAGE, KIND_TEXT, MODE_MOTION, MODE_TILED,
    TRAJECTORIES, TRAJECTORY_LABELS, WatermarkConfig,
)
from .batch_dialog import BatchDialog

# QSettings 组织/应用名（ffmpeg 二进制设置等 GUI 偏好的持久化）
_SETTINGS_ORG = "VideoWatermark"
_SETTINGS_APP = "VideoWatermark"

FF_MODE_AUTO = "auto"          # 自动（推荐）：交给 ffbin 解析层决策
FF_MODE_INTERNAL = "internal"  # 强制使用内置二进制
FF_MODE_CUSTOM = "custom"      # 使用自定义路径


def _wrap_grow(label: QLabel) -> QLabel:
    """自动换行标签：打开 sizePolicy 的 heightForWidth 标志。

    QLabel 默认的 sizePolicy 不带该标志，QFormLayout/QHBoxLayout 计算行高时
    只用 sizeHint 而不按当前宽度查询 heightForWidth——动态 setText 成多行
    （如长路径换行）后行高不够，文字会压到相邻控件上（v0.5.1 修复）。
    """
    sp = label.sizePolicy()
    sp.setHeightForWidth(True)
    label.setSizePolicy(sp)
    return label


def load_ffmpeg_setting() -> tuple[str, str]:
    """读取已保存的 ffmpeg 二进制设置，返回 (mode, path)。"""
    s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    return (str(s.value("ffmpeg/mode", FF_MODE_AUTO)),
            str(s.value("ffmpeg/path", "")))


def apply_ffmpeg_setting_to_env(mode: str, path: str) -> None:
    """把已保存的设置写入环境变量（须在 ffbin 首次解析前调用）。"""
    if mode == FF_MODE_CUSTOM and path:
        os.environ["VIDEO_WATERMARK_FFMPEG"] = path
    elif mode == FF_MODE_INTERNAL:
        os.environ["VIDEO_WATERMARK_FFMPEG"] = FF_MODE_INTERNAL
    else:
        os.environ.pop("VIDEO_WATERMARK_FFMPEG", None)


def pil_to_pixmap(img) -> QPixmap:
    """PIL 图像 -> QPixmap（RGB / RGBA）。"""
    if img.mode == "RGBA":
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)
    else:
        if img.mode != "RGB":
            img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class RenderWorker(QThread):
    """后台导出线程：编码在子线程执行，避免阻塞界面。"""
    progress = Signal(int, int)
    done = Signal(dict)
    error = Signal(str)

    def __init__(self, input_path: str, output_path: str, cfg: WatermarkConfig,
                 crf: int = 23, preset: str = "medium", scale: float = 1.0,
                 hw_encoder: str = "auto", hw_codec: str = "h264",
                 hw_decode: bool = True, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.cfg = cfg
        self.crf = crf
        self.preset = preset
        self.scale = scale
        self.hw_encoder = hw_encoder
        self.hw_codec = hw_codec
        self.hw_decode = hw_decode

    def run(self):
        try:
            stats = process(self.input_path, self.output_path, self.cfg,
                            progress_cb=self._on_progress,
                            crf=self.crf, preset=self.preset, scale=self.scale,
                            hw_encoder=self.hw_encoder, hw_codec=self.hw_codec,
                            hw_decode=self.hw_decode)
            self.done.emit(stats)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    def _on_progress(self, done, total):
        self.progress.emit(done, total)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频水印工具")
        self.resize(1080, 720)

        self._worker: RenderWorker | None = None
        self._text_color = (255, 255, 255)
        self._stroke_color = (0, 0, 0)
        self._progress_start = None
        self._progress_prev = None
        # 帧速率滑动窗口采样（(已处理帧, 时刻)），用于平滑速率显示
        self._rate_samples = deque()

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        root.addWidget(self._build_param_panel(), 0)
        root.addWidget(self._build_preview_panel(), 1)
        self._sync_panels()
        self._init_ff_settings_ui()

    # ------------------------------------------------------------------
    # 参数面板
    # ------------------------------------------------------------------
    def _build_param_panel(self) -> QWidget:
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        # 左侧参数面板加宽（内容最小宽度约 537px），并强制隐藏横向滚动条
        panel.setFixedWidth(480)
        panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        lay = QVBoxLayout(body)

        # --- 输入 / 输出 ---
        file_box = QGroupBox("视频文件")
        fl = QFormLayout(file_box)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("选择输入视频...")
        in_row = QHBoxLayout()
        in_row.addWidget(self.input_edit, 1)
        in_btn = QPushButton("浏览…")
        in_btn.clicked.connect(self._pick_input)
        in_row.addWidget(in_btn)
        in_open = QPushButton("打开位置")
        in_open.setToolTip("在资源管理器中打开输入视频所在文件夹")
        in_open.clicked.connect(lambda: self._open_location(self.input_edit.text()))
        in_row.addWidget(in_open)
        fl.addRow("输入视频", in_row)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("未设置时自动生成到输入目录")
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_edit, 1)
        out_btn = QPushButton("浏览…")
        out_btn.clicked.connect(self._pick_output)
        out_row.addWidget(out_btn)
        out_open = QPushButton("打开位置")
        out_open.setToolTip("在资源管理器中打开输出视频所在文件夹")
        out_open.clicked.connect(lambda: self._open_location(self.output_edit.text()))
        out_row.addWidget(out_open)
        fl.addRow("输出视频", out_row)
        lay.addWidget(file_box)

        # --- 模式与来源 ---
        mode_box = QGroupBox("模式")
        ml = QHBoxLayout(mode_box)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("平铺水印（全屏铺满）", MODE_TILED)
        self.mode_combo.addItem("移动水印（轨迹运动）", MODE_MOTION)
        ml.addWidget(QLabel("模式:"))
        ml.addWidget(self.mode_combo, 1)
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("文字水印", KIND_TEXT)
        self.kind_combo.addItem("图片水印", KIND_IMAGE)
        ml.addWidget(QLabel("来源:"))
        ml.addWidget(self.kind_combo, 1)
        lay.addWidget(mode_box)

        # --- 文字设置 ---
        self.text_box = QGroupBox("文字设置")
        tl = QFormLayout(self.text_box)
        self.text_edit = QTextEdit()
        self.text_edit.setFixedHeight(70)
        self.text_edit.setPlainText("CONFIDENTIAL\n机密内容")
        tl.addRow("内容(多行)", self.text_edit)

        self.font_combo = QComboBox()
        fonts = list_available_fonts()
        for f in fonts:
            self.font_combo.addItem(f, f)
        default_idx = self.font_combo.findText("微软雅黑")
        self.font_combo.setCurrentIndex(default_idx if default_idx >= 0 else 0)
        tl.addRow("字体", self.font_combo)

        self.font_size_spin = self._spin(8, 400, 48)
        tl.addRow("字号", self.font_size_spin)

        self.text_color_btn = self._color_button(self._text_color)
        tl.addRow("颜色", self.text_color_btn)

        self.text_opacity_slider = self._slider(255, 90)
        self.text_opacity_label = QLabel("90")
        tl.addRow("透明度", self._slider_row(self.text_opacity_slider, self.text_opacity_label))

        self.stroke_width_spin = self._spin(0, 20, 0)
        tl.addRow("描边宽度", self.stroke_width_spin)
        self.stroke_color_btn = self._color_button(self._stroke_color)
        tl.addRow("描边颜色", self.stroke_color_btn)
        lay.addWidget(self.text_box)

        # --- 图片设置 ---
        self.image_box = QGroupBox("图片设置")
        il = QFormLayout(self.image_box)
        self.image_path_edit = QLineEdit()
        img_row = QHBoxLayout()
        img_row.addWidget(self.image_path_edit, 1)
        img_btn = QPushButton("浏览…")
        img_btn.clicked.connect(self._pick_image)
        img_row.addWidget(img_btn)
        il.addRow("图片", img_row)

        self.img_scale_spin = self._dspin(0.05, 1.0, 0.3, 0.05)
        il.addRow("缩放(占帧宽)", self.img_scale_spin)
        self.img_opacity_slider = self._slider(255, 128)
        self.img_opacity_label = QLabel("128")
        il.addRow("透明度", self._slider_row(self.img_opacity_slider, self.img_opacity_label))
        self.img_radius_spin = self._spin(0, 200, 0)
        il.addRow("圆角(px)", self.img_radius_spin)
        lay.addWidget(self.image_box)

        # --- 平铺参数 ---
        self.tiled_box = QGroupBox("平铺参数（全屏平铺）")
        tdl = QFormLayout(self.tiled_box)
        self.angle_spin = self._dspin(-180.0, 180.0, 30.0, 1.0)
        tdl.addRow("旋转角度(°)", self.angle_spin)
        self.dx_spin = self._spin(50, 2000, 320)
        tdl.addRow("横向间距", self.dx_spin)
        self.dy_spin = self._spin(50, 2000, 200)
        tdl.addRow("纵向间距", self.dy_spin)
        self.offset_x_spin = self._spin(-2000, 2000, 0)
        tdl.addRow("偏移 X", self.offset_x_spin)
        self.offset_y_spin = self._spin(-2000, 2000, 0)
        tdl.addRow("偏移 Y", self.offset_y_spin)
        lay.addWidget(self.tiled_box)

        # --- 移动参数 ---
        self.motion_box = QGroupBox("移动参数（轨迹）")
        mol = QFormLayout(self.motion_box)
        self.trajectory_combo = QComboBox()
        for tr in TRAJECTORIES:
            self.trajectory_combo.addItem(TRAJECTORY_LABELS[tr], tr)
        mol.addRow("轨迹", self.trajectory_combo)

        self.speed_spin = self._dspin(0.1, 5.0, 1.0, 0.1)
        mol.addRow("速度倍率", self.speed_spin)
        self.motion_scale_spin = self._dspin(0.05, 1.0, 0.2, 0.05)
        mol.addRow("大小(占帧宽)", self.motion_scale_spin)
        self.motion_opacity_slider = self._slider(255, 200)
        self.motion_opacity_label = QLabel("200")
        mol.addRow("透明度", self._slider_row(self.motion_opacity_slider, self.motion_opacity_label))
        self.rotate_check = QCheckBox("随时间自转（每周期转一圈）")
        mol.addRow(self.rotate_check)
        lay.addWidget(self.motion_box)

        # --- 时间范围 ---
        time_box = QGroupBox("出现时间范围（秒）")
        tml = QFormLayout(time_box)
        self.start_spin = self._dspin(0.0, 3600.0, 0.0, 0.1)
        tml.addRow("开始时间", self.start_spin)
        self.end_check = QCheckBox("设置结束时间")
        self.end_check.setChecked(False)
        tml.addRow(self.end_check)
        self.end_spin = self._dspin(0.1, 3600.0, 5.0, 0.1)
        self.end_spin.setEnabled(False)
        self.end_check.toggled.connect(self.end_spin.setEnabled)
        tml.addRow("结束时间", self.end_spin)
        lay.addWidget(time_box)

        # --- 输出设置 ---
        out_box = QGroupBox("输出设置（编码）")
        ol = QFormLayout(out_box)
        self.format_combo = QComboBox()
        self.format_combo.addItem("MP4（推荐）", "mp4")
        self.format_combo.addItem("MOV", "mov")
        self.format_combo.addItem("MKV", "mkv")
        self.format_combo.addItem("AVI", "avi")
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        ol.addRow("输出格式", self.format_combo)

        self.crf_slider = self._slider(51, 23)
        self.crf_label = QLabel("23")
        self.crf_slider.valueChanged.connect(lambda v: self.crf_label.setText(str(v)))
        ol.addRow("质量(CRF)", self._slider_row(self.crf_slider, self.crf_label))
        crf_hint = QLabel("CRF 越低质量越高、文件越大（0~51，推荐 18~28）")
        crf_hint.setStyleSheet("color:#888; font-size:11px;")
        crf_hint.setWordWrap(True)
        _wrap_grow(crf_hint)
        ol.addRow(crf_hint)

        self.preset_combo = QComboBox()
        for p in ("ultrafast", "superfast", "veryfast", "faster", "fast",
                  "medium", "slow", "slower", "veryslow"):
            self.preset_combo.addItem(p, p)
        self.preset_combo.setCurrentText("medium")
        ol.addRow("编码预设", self.preset_combo)
        preset_hint = QLabel("越快的预设编码越快、文件略大（ultrafast~veryslow）")
        preset_hint.setStyleSheet("color:#888; font-size:11px;")
        preset_hint.setWordWrap(True)
        _wrap_grow(preset_hint)
        ol.addRow(preset_hint)

        self.scale_spin = self._dspin(0.1, 2.0, 1.0, 0.05)
        ol.addRow("分辨率缩放", self.scale_spin)
        scale_hint = QLabel("1.0 = 原分辨率；0.5 = 缩小一半；2.0 = 放大一倍")
        scale_hint.setStyleSheet("color:#888; font-size:11px;")
        scale_hint.setWordWrap(True)
        _wrap_grow(scale_hint)
        ol.addRow(scale_hint)

        # 硬件加速（GPU 编码/解码）
        self.hw_encoder_combo = QComboBox()
        for label, val in (
            ("自动（推荐）", "auto"),
            ("关闭（纯 CPU）", "none"),
            ("NVIDIA NVENC", "nvenc"),
            ("Intel QSV", "qsv"),
            ("AMD AMF", "amf"),
            ("Microsoft D3D12VA", "d3d12va"),
            ("MediaFoundation", "mf"),
        ):
            self.hw_encoder_combo.addItem(label, val)
        self.hw_encoder_combo.currentIndexChanged.connect(self._on_hw_changed)
        ol.addRow("硬件编码", self.hw_encoder_combo)

        self.hw_codec_combo = QComboBox()
        self.hw_codec_combo.addItem("H.264", "h264")
        self.hw_codec_combo.addItem("HEVC (H.265)", "hevc")
        ol.addRow("视频编码", self.hw_codec_combo)

        self.hw_decode_check = QCheckBox("启用硬件解码（失败自动回退）")
        self.hw_decode_check.setChecked(True)
        ol.addRow(self.hw_decode_check)

        # ffmpeg 二进制来源（v0.4.0：自动 / 内置 / 自定义路径，QSettings 持久化）
        self.ff_combo = QComboBox()
        self.ff_combo.addItem("自动（推荐）", FF_MODE_AUTO)
        self.ff_combo.addItem("内置二进制", FF_MODE_INTERNAL)
        self.ff_combo.addItem("自定义路径…", FF_MODE_CUSTOM)
        self.ff_combo.currentIndexChanged.connect(self._on_ff_mode_changed)
        ol.addRow("ffmpeg 二进制", self.ff_combo)

        ff_path_row = QHBoxLayout()
        self.ff_path_edit = QLineEdit()
        self.ff_path_edit.setPlaceholderText(
            "自定义 ffmpeg 路径（选择「自定义路径…」时生效）")
        self.ff_path_edit.editingFinished.connect(self._on_ff_path_edited)
        self.ff_browse_btn = QPushButton("浏览…")
        self.ff_browse_btn.clicked.connect(self._on_ff_browse)
        ff_path_row.addWidget(self.ff_path_edit, 1)
        ff_path_row.addWidget(self.ff_browse_btn)
        ol.addRow(ff_path_row)
        self.ff_status_label = QLabel("")
        self.ff_status_label.setStyleSheet("color:#888; font-size:11px;")
        self.ff_status_label.setWordWrap(True)
        _wrap_grow(self.ff_status_label)
        ol.addRow(self.ff_status_label)

        hw_info_row = QHBoxLayout()
        self.hw_info_label = QLabel("可用硬件编码器将在生成或点击检测时自动识别")
        self.hw_info_label.setStyleSheet("color:#888; font-size:11px;")
        self.hw_info_label.setWordWrap(True)
        _wrap_grow(self.hw_info_label)
        detect_btn = QPushButton("检测")
        detect_btn.setToolTip("探测当前机器的可用硬件编码器")
        detect_btn.clicked.connect(self._detect_hw)
        hw_info_row.addWidget(self.hw_info_label, 1)
        hw_info_row.addWidget(detect_btn)
        ol.addRow(hw_info_row)
        # 多行检测结果独立成行：与按钮同处 QHBoxLayout 的换行 QLabel 行高不可靠，
        # 长路径换行后会压到上下控件（v0.5.1 修复，见 _detect_hw）
        self.hw_detail_label = QLabel("")
        self.hw_detail_label.setStyleSheet("color:#888; font-size:11px;")
        self.hw_detail_label.setWordWrap(True)
        _wrap_grow(self.hw_detail_label)
        self.hw_detail_label.setVisible(False)
        ol.addRow(self.hw_detail_label)
        hw_hint = QLabel("硬件编码可大幅加速导出（NVENC/QSV/AMF）；无 GPU 时自动回退 CPU 编码")
        hw_hint.setStyleSheet("color:#888; font-size:11px;")
        hw_hint.setWordWrap(True)
        _wrap_grow(hw_hint)
        ol.addRow(hw_hint)
        lay.addWidget(out_box)

        lay.addStretch(1)
        panel.setWidget(body)
        return panel

    # ------------------------------------------------------------------
    # 预览面板
    # ------------------------------------------------------------------
    def _build_preview_panel(self) -> QWidget:
        right = QWidget()
        lay = QVBoxLayout(right)

        self.info_label = QLabel("请选择输入视频")
        self.info_label.setWordWrap(True)
        _wrap_grow(self.info_label)
        lay.addWidget(self.info_label)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("预览时间(s):"))
        self.preview_time_spin = self._dspin(0.0, 3600.0, 0.0, 0.1)
        ctrl.addWidget(self.preview_time_spin)
        prev_btn = QPushButton("预览帧")
        prev_btn.clicked.connect(self._on_preview)
        ctrl.addWidget(prev_btn)
        sketch_btn = QPushButton("轨迹示意")
        sketch_btn.clicked.connect(self._on_sketch)
        ctrl.addWidget(sketch_btn)
        ctrl.addStretch(1)
        lay.addLayout(ctrl)

        # 预览画布
        self.preview_label = QLabel("（预览区）")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(480, 320)
        self.preview_label.setStyleSheet(
            "background:#202020; color:#999; border:1px solid #444;")
        self.preview_label.setScaledContents(False)
        self._last_pixmap = None
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.preview_label)
        lay.addWidget(scroll, 1)

        # 导出
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)
        self.progress_status = QLabel("")
        self.progress_status.setWordWrap(True)
        _wrap_grow(self.progress_status)
        self.progress_status.setStyleSheet("color:#888; font-size:12px;")
        self.progress_status.setVisible(False)
        lay.addWidget(self.progress_status)

        export_btn = QPushButton("生成视频")
        export_btn.clicked.connect(self._on_export)
        export_btn.setMinimumHeight(40)
        batch_btn = QPushButton("批量处理…")
        batch_btn.clicked.connect(self._on_batch)
        batch_btn.setMinimumHeight(40)
        action_row = QHBoxLayout()
        action_row.addWidget(export_btn, 2)
        action_row.addWidget(batch_btn, 1)
        lay.addLayout(action_row)
        self._export_btn = export_btn
        self._batch_btn = batch_btn
        return right

    # ------------------------------------------------------------------
    # 工具函数
    # ------------------------------------------------------------------
    def _spin(self, lo, hi, val) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        return s

    def _dspin(self, lo, hi, val, step) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setSingleStep(step)
        s.setDecimals(1)
        return s

    def _slider(self, maxv, val) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, maxv)
        s.setValue(val)
        return s

    def _slider_row(self, slider, label) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(slider, 1)
        lay.addWidget(label)
        slider.valueChanged.connect(lambda v: label.setText(str(v)))
        return w

    def _color_button(self, initial):
        btn = QPushButton()
        btn.setFixedSize(48, 24)
        state = {"color": tuple(initial)}

        def set_color(c):
            state["color"] = tuple(c)
            btn.setStyleSheet(
                f"background-color:rgb({c[0]},{c[1]},{c[2]});border:1px solid #888;")

        set_color(initial)

        def pick():
            c = QColorDialog.getColor(QColor(*state["color"]), self, "选择颜色")
            if c.isValid():
                set_color((c.red(), c.green(), c.blue()))

        btn.clicked.connect(pick)
        btn._get_color = lambda: tuple(state["color"])  # noqa: B010
        return btn

    def _text_color_value(self):
        return self.text_color_btn._get_color()

    def _stroke_color_value(self):
        return self.stroke_color_btn._get_color()

    # ------------------------------------------------------------------
    # 配置构建 / 面板联动
    # ------------------------------------------------------------------
    def _cfg_from_ui(self) -> WatermarkConfig:
        cfg = WatermarkConfig()
        cfg.mode = self.mode_combo.currentData()
        cfg.kind = self.kind_combo.currentData()
        cfg.text = self.text_edit.toPlainText()
        cfg.font_name = self.font_combo.currentData() or ""
        cfg.font_size = self.font_size_spin.value()
        cfg.text_color = self._text_color_value()
        cfg.text_opacity = self.text_opacity_slider.value()
        cfg.stroke_width = self.stroke_width_spin.value()
        cfg.stroke_color = self._stroke_color_value()
        cfg.image_path = self.image_path_edit.text()
        cfg.img_scale = self.img_scale_spin.value()
        cfg.img_opacity = self.img_opacity_slider.value()
        cfg.img_radius = self.img_radius_spin.value()
        cfg.angle = self.angle_spin.value()
        cfg.tile_dx = self.dx_spin.value()
        cfg.tile_dy = self.dy_spin.value()
        cfg.offset_x = self.offset_x_spin.value()
        cfg.offset_y = self.offset_y_spin.value()
        cfg.trajectory = self.trajectory_combo.currentData()
        cfg.speed = self.speed_spin.value()
        cfg.motion_scale = self.motion_scale_spin.value()
        cfg.motion_opacity = self.motion_opacity_slider.value()
        cfg.motion_rotate = self.rotate_check.isChecked()
        cfg.start_sec = self.start_spin.value()
        cfg.end_sec = self.end_spin.value() if self.end_check.isChecked() else None
        return cfg

    def _sync_panels(self):
        def on_mode():
            is_motion = self.mode_combo.currentData() == MODE_MOTION
            self.tiled_box.setVisible(not is_motion)
            self.motion_box.setVisible(is_motion)

        def on_kind():
            is_text = self.kind_combo.currentData() == KIND_TEXT
            self.text_box.setVisible(is_text)
            self.image_box.setVisible(not is_text)

        self.mode_combo.currentIndexChanged.connect(on_mode)
        self.kind_combo.currentIndexChanged.connect(on_kind)
        on_mode()
        on_kind()

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def _pick_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择输入视频", "", "视频 (*.mp4 *.mov *.avi *.mkv *.webm *.flv);;所有文件 (*)")
        if path:
            self.input_edit.setText(path)
            try:
                meta = probe(path)
                self.info_label.setText(
                    f"输入视频：{os.path.basename(path)}\n"
                    f"分辨率 {meta['width']}×{meta['height']}  |  "
                    f"{meta['fps']:.2f} fps  |  时长约 {meta['duration_sec']:.1f}s")
                if not self.output_edit.text():
                    self.output_edit.setText(os.path.splitext(path)[0] + "_水印.mp4")
            except Exception as exc:
                self.info_label.setText(f"无法读取视频：{exc}")

    def _pick_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "选择输出视频", "", "MP4 视频 (*.mp4);;所有文件 (*)")
        if path:
            self.output_edit.setText(path)

    def _open_location(self, path: str):
        """在资源管理器中打开指定文件所在位置（若文件不存在则打开其目录）。"""
        path = path.strip().strip('"')
        if not path:
            QMessageBox.information(self, "提示", "请先填写要打开的路径")
            return
        folder = os.path.dirname(os.path.abspath(path))
        if os.path.isfile(path):
            # 文件存在 -> 资源管理器中选中该文件
            popen_hidden(f'explorer /select,"{os.path.abspath(path)}"')
        elif os.path.isdir(folder):
            # 文件不存在（如尚未生成的输出）-> 打开其所在目录
            popen_hidden(f'explorer "{folder}"')
        else:
            QMessageBox.warning(self, "提示", f"路径不存在：{path}")

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片水印", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)")
        if path:
            self.image_path_edit.setText(path)

    def _on_format_changed(self):
        """切换输出格式时同步更新输出文件扩展名。"""
        ext = self.format_combo.currentData()
        path = self.output_edit.text()
        if not path:
            return
        known = (".mp4", ".mov", ".mkv", ".avi")
        stem, cur = os.path.splitext(path)
        if cur.lower() in known:
            self.output_edit.setText(stem + "." + ext)

    def _on_hw_changed(self):
        """硬件编码关闭时，视频编码（h264/hevc）选择不可用（libx264 固定 H.264）。"""
        self.hw_codec_combo.setEnabled(self.hw_encoder_combo.currentData() != "none")

    # -- ffmpeg 二进制设置（v0.4.0） ------------------------------------

    def _init_ff_settings_ui(self):
        """构造完成后调用：按已保存设置初始化控件状态。"""
        mode, path = load_ffmpeg_setting()
        idx = self.ff_combo.findData(mode)
        self.ff_combo.blockSignals(True)
        self.ff_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.ff_combo.blockSignals(False)
        self.ff_path_edit.setText(path)
        self.ff_path_edit.setEnabled(mode == FF_MODE_CUSTOM)
        self.ff_browse_btn.setEnabled(mode == FF_MODE_CUSTOM)
        self.ff_status_label.setText(self._ff_status_text())

    def _ff_status_text(self) -> str:
        """当前生效的二进制摘要（探测过才有内容，否则留空避免误启动解析）。"""
        try:
            info = ffbin.info()
        except Exception:  # noqa: BLE001
            return ""
        return f"当前使用：{info['exe']}（{info['source']}）"

    def _save_ff_setting(self):
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        s.setValue("ffmpeg/mode", self.ff_combo.currentData())
        s.setValue("ffmpeg/path", self.ff_path_edit.text().strip())

    def _apply_ff_setting(self):
        """把 UI 选择写入环境变量并使解析/探测缓存失效（下次生成/检测生效）。"""
        mode = self.ff_combo.currentData()
        path = self.ff_path_edit.text().strip()
        apply_ffmpeg_setting_to_env(mode, path)
        ffbin.reset()
        from ..core import hwaccel as _hw
        _hw.detect_encoders.cache_clear()
        _hw.hw_decoder_names.cache_clear()

    def _on_ff_mode_changed(self):
        mode = self.ff_combo.currentData()
        self.ff_path_edit.setEnabled(mode == FF_MODE_CUSTOM)
        self.ff_browse_btn.setEnabled(mode == FF_MODE_CUSTOM)
        self._save_ff_setting()
        self._apply_ff_setting()
        self.ff_status_label.setText(self._ff_status_text())

    def _on_ff_path_edited(self):
        self._save_ff_setting()
        self._apply_ff_setting()
        self.ff_status_label.setText(self._ff_status_text())

    def _on_ff_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 ffmpeg 可执行文件", self.ff_path_edit.text())
        if path:
            self.ff_path_edit.setText(path)
            self._on_ff_path_edited()

    def _detect_hw(self):
        """探测当前机器可用的硬件编码器并显示结果（附当前使用的二进制）。

        多行结果写入独立整行的 hw_detail_label：与「检测」按钮同处一个
        QHBoxLayout 的换行 QLabel 在长文本（如打包后的长 ffmpeg 路径）换行时
        行高撑不开、文字压到相邻控件（v0.5.1 修复）；同行 hw_info_label 只放
        单行摘要。
        """
        self.hw_detail_label.setVisible(True)
        try:
            text = describe_available()
            info = ffbin.info()
            text += f"\n当前 ffmpeg：{info['exe']}（{info['source']}）"
            self.hw_detail_label.setText(text)
            avail = detect_encoders()
            self.hw_info_label.setText(
                "检测完成"
                if avail else "检测完成：未检测到硬件编码器（回退 CPU 编码）")
        except Exception as exc:  # noqa: BLE001
            self.hw_info_label.setText("检测失败：")
            self.hw_detail_label.setText(str(exc))

    def _on_preview(self):
        input_path = self.input_edit.text()
        if not os.path.isfile(input_path):
            QMessageBox.warning(self, "提示", "请先选择输入视频")
            return
        try:
            cfg = self._cfg_from_ui()
            img = preview.render_preview_frame(
                input_path, cfg, self.preview_time_spin.value())
            self._show_image(img)
        except Exception as exc:
            QMessageBox.critical(self, "预览失败", str(exc))

    def _on_sketch(self):
        input_path = self.input_edit.text()
        if not os.path.isfile(input_path):
            QMessageBox.warning(self, "提示", "请先选择输入视频（用于获取帧尺寸）")
            return
        try:
            meta = probe(input_path)
            cfg = self._cfg_from_ui()
            img = preview.sketch_trajectory(cfg, meta["width"], meta["height"])
            self._show_image(img)
        except Exception as exc:
            QMessageBox.critical(self, "轨迹示意失败", str(exc))

    def _show_image(self, img):
        self._last_pixmap = pil_to_pixmap(img)
        self.preview_label.setPixmap(self._last_pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_pixmap is not None and not self._last_pixmap.isNull():
            self.preview_label.setPixmap(self._last_pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def _on_export(self):
        input_path = self.input_edit.text()
        if not os.path.isfile(input_path):
            QMessageBox.warning(self, "提示", "请先选择输入视频")
            return
        output_path = self.output_edit.text().strip()
        if not output_path:
            output_path = os.path.splitext(input_path)[0] + "_水印.mp4"
            self.output_edit.setText(output_path)
        if os.path.abspath(input_path) == os.path.abspath(output_path):
            QMessageBox.warning(self, "提示", "输出文件不能与输入相同")
            return
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在生成中，请稍候")
            return

        cfg = self._cfg_from_ui()
        self._export_btn.setEnabled(False)
        self._progress_start = None
        self._progress_prev = None
        self._rate_samples.clear()
        self.progress_bar.setVisible(True)
        self.progress_status.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.progress_status.setText("正在处理…")

        self._worker = RenderWorker(
            input_path, output_path, cfg,
            crf=self.crf_slider.value(),
            preset=self.preset_combo.currentData() or "medium",
            scale=self.scale_spin.value(),
            hw_encoder=self.hw_encoder_combo.currentData() or "auto",
            hw_codec=self.hw_codec_combo.currentData() or "h264",
            hw_decode=self.hw_decode_check.isChecked(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @staticmethod
    def _format_eta(sec: float) -> str:
        sec = max(0, int(sec))
        return f"{sec // 60}:{sec % 60:02d}"

    def _on_progress(self, done, total):
        if self._progress_start is None:
            self._progress_start = time.monotonic()
            self._progress_prev = (0, self._progress_start)
        now = time.monotonic()
        if total and total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(min(done, total))
            self.progress_bar.setFormat("第 %v/%m 帧 (%p%)")
            pct = done * 100 // total
            # 滑动窗口（约 2s）内平均速率：避免瞬时速率抖动导致文字闪烁
            self._rate_samples.append((done, now))
            while (len(self._rate_samples) > 2
                   and now - self._rate_samples[0][1] > 2.0):
                self._rate_samples.popleft()
            rate = 0.0
            if len(self._rate_samples) >= 2:
                d0, t0 = self._rate_samples[0]
                d1, t1 = self._rate_samples[-1]
                if d1 > d0 and t1 > t0:
                    rate = (d1 - d0) / (t1 - t0)
            # 节流刷新文本（每 0.3s），文案格式恒定：始终带速率，避免闪烁
            if now - self._progress_prev[1] >= 0.3 or done >= total:
                if rate > 0:
                    eta = (total - done) / rate
                    self.progress_status.setText(
                        f"正在处理… 第 {done}/{total} 帧 ({pct}%)  "
                        f"≈{rate:.1f} 帧/秒  剩余约 {self._format_eta(eta)}")
                else:
                    self.progress_status.setText(
                        f"正在处理… 第 {done}/{total} 帧 ({pct}%)")
                self._progress_prev = (done, now)
        else:
            self.progress_bar.setRange(0, 0)  # 忙碌模式
            self.progress_status.setText("正在处理…（无法获取总帧数）")

    def _on_done(self, stats):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("")
        self.progress_status.setText("处理完成")
        self._export_btn.setEnabled(True)
        codec = stats.get("codec", "libx264")
        hw_note = "（硬件编码）" if codec and codec != "libx264" else "（CPU 编码）"
        QMessageBox.information(
            self, "完成",
            f"生成完成：{stats['width']}×{stats['height']}，共 {stats['frames']} 帧\n"
            f"编码器：{codec} {hw_note}\n"
            f"输出：{self.output_edit.text()}")

    def _on_error(self, msg):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFormat("")
        self.progress_status.setText("处理失败")
        self._export_btn.setEnabled(True)
        QMessageBox.critical(self, "生成失败", str(msg))

    def _on_batch(self):
        """打开批量处理对话框（沿用当前水印与编码设置）。"""
        cfg = self._cfg_from_ui()
        ext = self.format_combo.currentData() or "mp4"
        dlg = BatchDialog(
            self, cfg,
            crf=self.crf_slider.value(),
            preset=self.preset_combo.currentData() or "medium",
            scale=self.scale_spin.value(),
            out_ext=ext,
            hw_encoder=self.hw_encoder_combo.currentData() or "auto",
            hw_codec=self.hw_codec_combo.currentData() or "h264",
            hw_decode=self.hw_decode_check.isChecked(),
        )
        dlg.exec()

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            ret = QMessageBox.question(
                self, "确认", "正在生成视频，确定退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.wait(3000)
        event.accept()
