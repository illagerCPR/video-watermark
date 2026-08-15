"""步骤 4 测试：批量处理端到端（多文件 + 并行/串行 + 帧级进度 + 产物校验）。

运行：  .venv\\Scripts\\python.exe scripts\\step4_batch_test.py
注意：批量并行使用进程池，脚本必须带 __main__ 保护，否则子进程会递归执行。
"""
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.models import WatermarkConfig, MODE_TILED, KIND_TEXT  # noqa: E402
from app.ui.batch_dialog import BatchDialog  # noqa: E402

OUT = ROOT / "outputs"
SAMPLE = OUT / "sample_video.mp4"
WORK = OUT / "_batch_test"
BATCH_OUT = WORK / "out"

failures = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


def run_batch(parallel, n_files, label):
    """跑一批批量处理，收集逐帧进度信号并校验产物。"""
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    BATCH_OUT.mkdir(parents=True)

    inputs = []
    for i, name in enumerate(("a.mp4", "b.mp4", "c.mp4")):
        if i >= n_files:
            break
        p = WORK / name
        shutil.copy2(SAMPLE, p)
        inputs.append(str(p))

    app = QApplication.instance() or QApplication(sys.argv)
    dlg = BatchDialog(None, WatermarkConfig(kind=KIND_TEXT, mode=MODE_TILED,
                                            text="批量测试", angle=45),
                      crf=23, preset="veryfast", scale=1.0, out_ext="mp4")
    dlg.parallel_spin.setValue(parallel)
    dlg._append(inputs)
    check(f"[{label}] 列表包含 {n_files} 个文件", dlg.file_list.count() == n_files)
    dlg.out_dir_edit.setText(str(BATCH_OUT))

    state = {"done": False}
    results = {}
    frame_seen = {}  # 文件序号 -> (已到帧数, 总帧数)

    dlg._start()
    if dlg._worker is None:
        return f"worker 未启动（{label}）"
    dlg._worker.all_done.connect(lambda ok, fail: (
        results.update(ok=ok, fail=fail), state.update(done=True)))
    dlg._worker.frame_progress.connect(
        lambda idx, d, t: frame_seen.__setitem__(
            idx, (max(frame_seen.get(idx, (0, t))[0], d), t)))

    def poll():
        if not state["done"] and dlg._worker.isRunning():
            QTimer.singleShot(200, poll)
        else:
            app.quit()

    QTimer.singleShot(200, poll)
    app.exec()

    check(f"[{label}] {n_files} 个全部成功",
          results.get("ok") == n_files and results.get("fail", -1) == 0,
          f"ok={results.get('ok')} fail={results.get('fail')}")
    outs = sorted(BATCH_OUT.glob("*.mp4")) if BATCH_OUT.exists() else []
    check(f"[{label}] 输出 {n_files} 个文件", len(outs) == n_files,
          f"产出 {len(outs)} 个")
    check(f"[{label}] 命名规则 原名_水印", all("_水印" in p.name for p in outs),
          " | ".join(p.name for p in outs))
    for p in outs:
        check(f"[{label}] 文件有效 {p.name}", os.path.getsize(p) > 5000,
              f"{os.path.getsize(p)} 字节")

    # 帧级进度：收到信号且每个文件都推进到总帧数（SAMPLE 共 150 帧）
    check(f"[{label}] 收到帧级进度信号", len(frame_seen) > 0,
          f"覆盖 {len(frame_seen)} 个文件")
    complete = bool(frame_seen) and all(d >= t for d, t in frame_seen.values())
    check(f"[{label}] 帧进度推进到总帧数", complete, f"{dict(frame_seen)}")
    return None


def main() -> int:
    # 入口 freeze_support 保护（打包 exe 批量并行的关键修复）
    main_src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    check("入口含 freeze_support 保护", "freeze_support()" in main_src)

    err = run_batch(parallel=3, n_files=3, label="并行=3")
    if err:
        print("[FAIL]", err)
        return 1
    err = run_batch(parallel=1, n_files=2, label="串行=1")
    if err:
        print("[FAIL]", err)
        return 1

    shutil.rmtree(WORK, ignore_errors=True)
    print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
