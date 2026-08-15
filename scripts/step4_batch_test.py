"""步骤 4 测试：批量处理端到端（多文件 + 并行 + 逐文件进度 + 产物校验）。

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


def main() -> int:
    # 准备 3 个输入
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    inputs = []
    for i, name in enumerate(("a.mp4", "b.mp4", "c.mp4")):
        p = WORK / name
        shutil.copy2(SAMPLE, p)
        inputs.append(str(p))

    app = QApplication(sys.argv)
    dlg = BatchDialog(None, WatermarkConfig(kind=KIND_TEXT, mode=MODE_TILED,
                                            text="批量测试", angle=45),
                      crf=23, preset="veryfast", scale=1.0, out_ext="mp4")
    dlg.parallel_spin.setValue(3)  # 并行 3 个

    dlg._append(inputs)
    check("列表包含 3 个文件", dlg.file_list.count() == 3)
    dlg.out_dir_edit.setText(str(BATCH_OUT))

    state = {"done": False}
    results = {}

    # 批量开始
    dlg._start()
    if dlg._worker is not None:
        dlg._worker.all_done.connect(lambda ok, fail: (
            results.update(ok=ok, fail=fail), state.update(done=True)))

        def poll():
            if not state["done"] and dlg._worker.isRunning():
                QTimer.singleShot(200, poll)
            else:
                app.quit()

        QTimer.singleShot(200, poll)
        app.exec()
    else:
        results["error"] = "worker 未启动"

    if "error" in results:
        print("[FAIL]", results["error"])
        return 1

    check("3 个全部成功", results["ok"] == 3 and results["fail"] == 0,
          f"ok={results['ok']} fail={results['fail']}")
    outs = sorted(BATCH_OUT.glob("*.mp4")) if BATCH_OUT.exists() else []
    check("输出 3 个文件", len(outs) == 3, f"产出 {len(outs)} 个")
    check("命名规则 原名_水印", all("_水印" in p.name for p in outs),
          " | ".join(p.name for p in outs))
    for p in outs:
        check(f"文件有效 {p.name}", os.path.getsize(p) > 5000,
              f"{os.path.getsize(p)} 字节")

    shutil.rmtree(WORK, ignore_errors=True)
    print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
