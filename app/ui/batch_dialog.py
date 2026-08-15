"""批量处理对话框：多视频用同一套水印参数批量生成。

- 添加文件 / 添加文件夹（自动过滤视频格式）
- 输出到指定目录，命名：原名_水印.扩展名
- 后台线程顺序处理，逐文件进度 + 结果日志
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
)

from ..core.encoder import process
from ..models import WatermarkConfig

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".ts"}


class BatchWorker(QThread):
    file_progress = Signal(int, int)        # 当前文件 (done, total)
    file_finished = Signal(int, str, bool)  # (序号, 消息, 是否成功)
    all_done = Signal(int, int)             # (成功数, 失败数)

    def __init__(self, jobs: list[tuple[str, str]], cfg: WatermarkConfig,
                 crf: int, preset: str, scale: float, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.cfg = cfg
        self.crf = crf
        self.preset = preset
        self.scale = scale

    def run(self):
        ok = fail = 0
        for idx, (inp, out) in enumerate(self.jobs):
            try:
                process(inp, out, self.cfg, progress_cb=self._on_progress,
                        crf=self.crf, preset=self.preset, scale=self.scale)
                ok += 1
                self.file_finished.emit(idx, f"完成：{os.path.basename(out)}", True)
            except Exception as exc:  # noqa: BLE001
                fail += 1
                self.file_finished.emit(
                    idx, f"失败：{os.path.basename(inp)} —— {exc}", False)
        self.all_done.emit(ok, fail)

    def _on_progress(self, done, total):
        self.file_progress.emit(done, total)


class BatchDialog(QDialog):
    def __init__(self, parent, cfg: WatermarkConfig,
                 crf: int, preset: str, scale: float, out_ext: str):
        super().__init__(parent)
        self.cfg = cfg
        self.crf = crf
        self.preset = preset
        self.scale = scale
        self.out_ext = out_ext.lstrip(".")
        self._worker: BatchWorker | None = None

        self.setWindowTitle("批量处理")
        self.resize(640, 480)

        lay = QVBoxLayout(self)

        # 文件列表
        lay.addWidget(QLabel("待处理视频列表："))
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        lay.addWidget(self.file_list, 1)

        # 列表操作按钮
        btns = QHBoxLayout()
        add_files_btn = QPushButton("添加文件…")
        add_files_btn.clicked.connect(self._add_files)
        btns.addWidget(add_files_btn)
        add_dir_btn = QPushButton("添加文件夹…")
        add_dir_btn.clicked.connect(self._add_folder)
        btns.addWidget(add_dir_btn)
        remove_btn = QPushButton("移除选中")
        remove_btn.clicked.connect(self._remove_selected)
        btns.addWidget(remove_btn)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.file_list.clear)
        btns.addWidget(clear_btn)
        btns.addStretch(1)
        lay.addLayout(btns)

        # 输出目录
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("输出目录:"))
        self.out_dir_edit = QLineEdit()
        out_row.addWidget(self.out_dir_edit, 1)
        out_btn = QPushButton("浏览…")
        out_btn.clicked.connect(self._pick_outdir)
        out_row.addWidget(out_btn)
        lay.addLayout(out_row)

        # 进度
        self.file_progress = QProgressBar()
        self.file_progress.setRange(0, 100)
        self.file_progress.setValue(0)
        lay.addWidget(self.file_progress)
        self.status_label = QLabel("就绪")
        lay.addWidget(self.status_label)

        # 日志
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        lay.addWidget(self.log, 1)

        # 底部按钮
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.start_btn = QPushButton("开始批量处理")
        self.start_btn.clicked.connect(self._start)
        bottom.addWidget(self.start_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(close_btn)
        lay.addLayout(bottom)

    # ------------------------------------------------------------------
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "",
            "视频 (*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.m4v *.ts);;所有文件 (*)")
        self._append(paths)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not folder:
            return
        found = []
        for p in Path(folder).rglob("*"):
            if p.suffix.lower() in VIDEO_EXTS:
                found.append(str(p))
        if not found:
            QMessageBox.information(self, "提示", "该文件夹下未找到视频文件")
            return
        self._append(sorted(found))

    def _append(self, paths):
        existing = {self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.file_list.count())}
        for p in paths:
            if p not in existing:
                self.file_list.addItem(os.path.basename(p))
                self.file_list.item(self.file_list.count() - 1).setData(
                    Qt.ItemDataRole.UserRole, p)
        self._refresh_outdir()

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self._refresh_outdir()

    def _refresh_outdir(self):
        if self.out_dir_edit.text():
            return
        if self.file_list.count() > 0:
            first = self.file_list.item(0).data(Qt.ItemDataRole.UserRole)
            self.out_dir_edit.setText(os.path.join(os.path.dirname(first), "水印输出"))

    def _pick_outdir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.out_dir_edit.setText(folder)

    # ------------------------------------------------------------------
    def _start(self):
        if self._worker is not None and self._worker.isRunning():
            return
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "提示", "请先添加待处理的视频")
            return
        outdir = self.out_dir_edit.text().strip()
        if not outdir:
            QMessageBox.warning(self, "提示", "请选择输出目录")
            return
        Path(outdir).mkdir(parents=True, exist_ok=True)

        jobs = []
        for i in range(self.file_list.count()):
            inp = self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            stem = os.path.splitext(os.path.basename(inp))[0]
            out = os.path.join(outdir, f"{stem}_水印.{self.out_ext}")
            jobs.append((inp, out))

        self.start_btn.setEnabled(False)
        self.log.clear()
        self.file_progress.setValue(0)
        self.status_label.setText(f"开始处理 {len(jobs)} 个文件...")

        self._worker = BatchWorker(jobs, self.cfg, self.crf, self.preset, self.scale)
        self._worker.file_progress.connect(self._on_file_progress)
        self._worker.file_finished.connect(self._on_file_finished)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_file_progress(self, done, total):
        pct = done * 100 // total if total else 0
        self.file_progress.setValue(pct)
        self.status_label.setText(f"当前进度：{pct}% ({done}/{total} 帧)")

    def _on_file_finished(self, idx, msg, ok):
        self.log.appendPlainText(msg)
        self.status_label.setText(f"已完成 {idx + 1}/{self.file_list.count()}")

    def _on_all_done(self, ok, fail):
        self.file_progress.setValue(100)
        self.start_btn.setEnabled(True)
        self.status_label.setText(f"批量处理结束：成功 {ok}，失败 {fail}")
        QMessageBox.information(
            self, "批量处理完成", f"成功 {ok} 个，失败 {fail} 个\n输出目录："
            f"{self.out_dir_edit.text()}")

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "批量处理进行中，请稍候或等待完成")
            event.ignore()
            return
        event.accept()
