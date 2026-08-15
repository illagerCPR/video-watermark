"""批量处理对话框：多视频用同一套水印参数批量生成。

- 添加文件 / 添加文件夹（自动过滤视频格式）
- 输出到指定目录，命名：原名_水印.扩展名
- 支持并行：多进程同时处理 N 个视频（默认按 CPU 核数），逐文件进度 + 结果日志
"""
from __future__ import annotations

import concurrent.futures as cf
import multiprocessing
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
    QVBoxLayout,
)

from ..core.encoder import process
from ..models import WatermarkConfig

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".ts"}

# 跨进程帧进度回传的结束哨兵（字符串保证经过队列 pickle 往返后仍可比较）
_PROGRESS_END = "__BATCH_PROGRESS_END__"


def _run_one(inp, out, cfg, crf, preset, scale, hw_encoder, hw_codec, hw_decode,
             progress_q=None, idx=0):
    """供进程池调用的顶层函数（必须可 pickle，Windows spawn 要求）。

    progress_q 不为 None 时，把逐帧进度 (文件序号, done, total) 放进队列，
    由父进程的转发线程读出并发射 frame_progress 信号。
    """
    def _cb(done, ftotal):
        try:
            if progress_q is not None:
                progress_q.put((idx, done, ftotal))
        except Exception:  # noqa: BLE001 —— 进度上报失败不影响处理本身
            pass

    process(inp, out, cfg, crf=crf, preset=preset, scale=scale,
            hw_encoder=hw_encoder, hw_codec=hw_codec, hw_decode=hw_decode,
            progress_cb=_cb)


class BatchWorker(QThread):
    overall = Signal(int, int)              # (已完成文件数, 总文件数)
    file_finished = Signal(int, str, bool)  # (序号, 消息, 是否成功)
    frame_progress = Signal(int, int, int)  # (文件序号, 已完成帧, 总帧数)
    all_done = Signal(int, int)             # (成功数, 失败数)

    def __init__(self, jobs: list[tuple[str, str]], cfg: WatermarkConfig,
                 crf: int, preset: str, scale: float,
                 hw_encoder: str = "auto", hw_codec: str = "h264",
                 hw_decode: bool = True, parallel: int = 0,
                 progress_q=None, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.cfg = cfg
        self.crf = crf
        self.preset = preset
        self.scale = scale
        self.hw_encoder = hw_encoder
        self.hw_codec = hw_codec
        self.hw_decode = hw_decode
        self.parallel = parallel if parallel > 0 else min(4, os.cpu_count() or 1)
        # 跨进程帧进度队列：必须在主线程创建（Windows 下非主线程建 Queue 会 WinError 5），
        # 由 BatchDialog._start 在主线程创建后传入；None 表示并行模式不回传帧进度。
        self._progress_q = progress_q

    def run(self):
        ok = fail = 0
        total = len(self.jobs)
        if self.parallel <= 1 or total <= 1:
            # 串行（单文件/并行数=1）：帧进度直接回调发信号
            for idx, (inp, out) in enumerate(self.jobs):
                try:
                    process(inp, out, self.cfg, crf=self.crf, preset=self.preset,
                            scale=self.scale, hw_encoder=self.hw_encoder,
                            hw_codec=self.hw_codec, hw_decode=self.hw_decode,
                            progress_cb=lambda d, t, i=idx: self.frame_progress.emit(i, d, t))
                    ok += 1
                    self.file_finished.emit(idx, f"完成：{os.path.basename(out)}", True)
                except Exception as exc:  # noqa: BLE001
                    fail += 1
                    self.file_finished.emit(
                        idx, f"失败：{os.path.basename(inp)} —— {exc}", False)
                self.overall.emit(idx + 1, total)
            self.all_done.emit(ok, fail)
            return

        # 并行：多进程同时处理（进程池会真实并行解码/合成/编码）。
        # 子进程里的逐帧进度经 multiprocessing.Queue 传回，由转发线程发信号。
        # （队列由主线程创建传入；这里只读取/关闭，可在本线程操作。）
        progress_q = self._progress_q
        fwd = None
        if progress_q is not None:
            def forward():
                while True:
                    item = progress_q.get()
                    if item == _PROGRESS_END:
                        return
                    idx, done, ftotal = item
                    self.frame_progress.emit(idx, done, ftotal)

            fwd = threading.Thread(target=forward, daemon=True)
            fwd.start()
        try:
            with cf.ProcessPoolExecutor(max_workers=self.parallel) as pool:
                fut_map = {}
                for idx, (inp, out) in enumerate(self.jobs):
                    f = pool.submit(_run_one, inp, out, self.cfg, self.crf,
                                    self.preset, self.scale, self.hw_encoder,
                                    self.hw_codec, self.hw_decode,
                                    progress_q, idx)
                    fut_map[f] = idx
                done_count = 0
                for f in cf.as_completed(fut_map):
                    idx = fut_map[f]
                    try:
                        f.result()
                        ok += 1
                        self.file_finished.emit(idx, f"完成：{os.path.basename(self.jobs[idx][1])}", True)
                    except Exception as exc:  # noqa: BLE001
                        fail += 1
                        self.file_finished.emit(
                            idx, f"失败：{os.path.basename(self.jobs[idx][0])} —— {exc}", False)
                    done_count += 1
                    self.overall.emit(done_count, total)
        finally:
            # 池已退出，通知转发线程结束（队列与 Manager 由 _on_all_done 统一关停）
            if fwd is not None:
                try:
                    progress_q.put(_PROGRESS_END)
                    fwd.join(timeout=3)
                except Exception:  # noqa: BLE001
                    pass
        self.all_done.emit(ok, fail)


class BatchDialog(QDialog):
    def __init__(self, parent, cfg: WatermarkConfig,
                 crf: int, preset: str, scale: float, out_ext: str,
                 hw_encoder: str = "auto", hw_codec: str = "h264",
                 hw_decode: bool = True):
        super().__init__(parent)
        self.cfg = cfg
        self.crf = crf
        self.preset = preset
        self.scale = scale
        self.out_ext = out_ext.lstrip(".")
        self.hw_encoder = hw_encoder
        self.hw_codec = hw_codec
        self.hw_decode = hw_decode
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

        # 并行数
        par_row = QHBoxLayout()
        par_row.addWidget(QLabel("并行处理数:"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, min(8, os.cpu_count() or 1))
        self.parallel_spin.setValue(min(4, os.cpu_count() or 1))
        self.parallel_spin.setToolTip("同时处理的视频个数；越多占用 CPU/GPU 越高，批量吞吐越大")
        par_row.addWidget(self.parallel_spin)
        par_row.addWidget(QLabel("（多个视频同时处理，批量更快）"))
        par_row.addStretch(1)
        lay.addLayout(par_row)

        # 进度
        self.file_progress = QProgressBar()
        self.file_progress.setRange(0, 100)
        self.file_progress.setValue(0)
        lay.addWidget(self.file_progress)
        self.status_label = QLabel("就绪")
        lay.addWidget(self.status_label)

        # 帧级进度（当前处理文件）
        self.frame_bar = QProgressBar()
        self.frame_bar.setRange(0, 0)
        self.frame_bar.setFormat("")
        lay.addWidget(self.frame_bar)
        self.frame_label = QLabel("帧进度：—")
        self.frame_label.setStyleSheet("color:#888; font-size:12px;")
        lay.addWidget(self.frame_label)

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
        self.frame_bar.setRange(0, 0)
        self.frame_bar.setFormat("")
        self.frame_label.setText("帧进度：—")
        self._jobs = jobs
        # 跨进程帧进度队列：用 Manager().Queue()（代理对象可安全传给进程池 worker；
        # 原生 multiprocessing.Queue 只能靠继承共享，作参数传递会报
        # "Queue objects should only be shared through inheritance"）。
        # 必须在主线程创建；受限环境建失败时退回并行无帧进度，不阻断批量本身。
        self._progress_manager = None
        parallel = self.parallel_spin.value()
        progress_q = None
        if parallel >= 2 and len(jobs) > 1:
            try:
                self._progress_manager = multiprocessing.Manager()
                progress_q = self._progress_manager.Queue()
            except Exception:  # noqa: BLE001
                if self._progress_manager is not None:
                    try:
                        self._progress_manager.shutdown()
                    except Exception:  # noqa: BLE001
                        pass
                self._progress_manager = None
                progress_q = None
        self._worker = BatchWorker(jobs, self.cfg, self.crf, self.preset, self.scale,
                                   self.hw_encoder, self.hw_codec, self.hw_decode,
                                   parallel, progress_q=progress_q)
        self._worker.overall.connect(self._on_overall)
        self._worker.file_finished.connect(self._on_file_finished)
        self._worker.frame_progress.connect(self._on_frame_progress)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_overall(self, done, total):
        if total:
            self.file_progress.setValue(done * 100 // total)
        self.status_label.setText(f"已完成 {done}/{total} 个文件")

    def _on_file_finished(self, idx, msg, ok):
        self.log.appendPlainText(msg)
        self.status_label.setText(f"已完成 {idx + 1}/{self.file_list.count()}")

    def _on_frame_progress(self, idx, done, ftotal):
        jobs = getattr(self, "_jobs", None)
        name = os.path.basename(jobs[idx][0]) if jobs and idx < len(jobs) else f"文件{idx + 1}"
        if ftotal and ftotal > 0:
            self.frame_bar.setRange(0, ftotal)
            self.frame_bar.setValue(min(done, ftotal))
            self.frame_bar.setFormat("第 %v/%m 帧 (%p%)")
            pct = done * 100 // ftotal
            self.frame_label.setText(
                f"文件 {idx + 1}/{len(jobs)}：{name}  第 {done}/{ftotal} 帧 ({pct}%)")
        else:
            self.frame_bar.setRange(0, 0)  # 忙碌模式（总帧数未知）
            self.frame_label.setText(f"文件 {idx + 1}/{len(jobs)}：{name}  处理中…")

    def _on_all_done(self, ok, fail):
        self.file_progress.setValue(100)
        self.frame_bar.setRange(0, 1)
        self.frame_bar.setValue(1)
        self.frame_bar.setFormat("")
        self.frame_label.setText("帧进度：已完成")
        self.start_btn.setEnabled(True)
        self.status_label.setText(f"批量处理结束：成功 {ok}，失败 {fail}")
        # 关停 Manager 服务进程（负责跨进程帧进度队列）
        mgr = getattr(self, "_progress_manager", None)
        if mgr is not None:
            try:
                mgr.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self._progress_manager = None
        QMessageBox.information(
            self, "批量处理完成", f"成功 {ok} 个，失败 {fail} 个\n输出目录："
            f"{self.out_dir_edit.text()}")

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "批量处理进行中，请稍候或等待完成")
            event.ignore()
            return
        event.accept()
