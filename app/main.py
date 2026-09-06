"""程序入口：启动图形界面。

运行方式：
  python -m app.main          （推荐，需在项目根目录）
  python app/main.py
"""
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.ui.main_window import MainWindow
else:
    from .ui.main_window import MainWindow


def _selftest_double(x: int) -> int:
    """供 --selftest 的进程池子进程调用（模块级才能跨进程 pickle）。"""
    return x * 2


def _apply_app_icon(app) -> None:
    """设置窗口/任务栏图标。

    开发模式读取项目根目录 icon.ico；打包（PyInstaller onefile）后从
    sys._MEIPASS 读取内嵌副本（spec 已把 icon.ico 加入 datas）。
    图标缺失或加载失败时静默跳过，不影响启动。
    """
    from PySide6.QtGui import QIcon

    try:
        base = getattr(sys, "_MEIPASS", None)
        if base:
            ico = os.path.join(base, "icon.ico")
        else:
            ico = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "icon.ico")
        if os.path.isfile(ico):
            app.setWindowIcon(QIcon(ico))
    except Exception:  # noqa: BLE001
        pass

    # Windows 任务栏：设置显式 AppUserModelID，避免任务栏/标题栏使用默认图标
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "VideoWatermark")
    except Exception:  # noqa: BLE001
        pass


# --tui 时是否经由 AttachConsole 接管控制台（True=非控制台程序原生stdio，
# 而是 GUI 子系统 exe 附加到宿主终端；用于判断是否打印垫片提示）
_TUI_ATTACHED = False


def _setup_tui_console() -> bool:
    """TUI 模式（--tui）需要控制台。Windows GUI 子系统 exe 没有 stdio——
    尝试附加祖先进程的控制台并接好标准句柄；失败（如双击启动）返回 False。

    Linux/macOS 终端天然可用，直接返回 True。

    v0.5.1 修复（Windows Terminal 下 exe --tui 误弹"请从命令行启动"）：
    - PyInstaller onefile 的 GUI 引导器会插在 shell 与 python 子进程之间，
      ATTACH_PARENT_PROCESS 附加到的是**引导器**（无控制台），必然失败；
      现改为沿祖先链（Toolhelp32 快照）逐个 AttachConsole(pid)，第一个
      带控制台的祖先（powershell/cmd 所在终端）即为宿主。
    - ConPTY（Windows Terminal）下 GetConsoleWindow() 恒为 0，不能用它判断
      "有无控制台"；改用 GetStdHandle+GetConsoleMode（真控制台句柄才有效），
      AttachConsole 报 ERROR_ACCESS_DENIED 也说明本进程已带控制台。
    - Textual 的 Windows 驱动输出读 sys.__stdout__、输入读
      GetStdHandle(STD_INPUT_HANDLE)，故附加成功后须 SetStdHandle 三件套
      并同时重绑 sys.stdout / sys.__stdout__。

    环境变量 VIDEO_WATERMARK_TUI_DEBUG=1 时把判定过程写到
    %TEMP%/video_watermark_tui_debug.log（排查附加问题用）。
    """
    if sys.platform != "win32":
        return True
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    debug: list[str] = []

    def _log(msg: str) -> None:
        debug.append(msg)

    def _flush(ok: bool) -> None:
        if not os.environ.get("VIDEO_WATERMARK_TUI_DEBUG"):
            return
        try:
            path = os.path.join(
                os.environ.get("TEMP", os.getcwd()),
                "video_watermark_tui_debug.log")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"ok={ok} " + " | ".join(debug) + "\n")
        except Exception:  # noqa: BLE001
            pass

    # 1) stdout 已是控制台句柄（控制台子系统 python / bat 启动路径）——直接用
    STD_OUTPUT_HANDLE = -11  # pylint: disable=invalid-name
    k32.GetStdHandle.restype = wintypes.HANDLE
    hout = k32.GetStdHandle(wintypes.DWORD(STD_OUTPUT_HANDLE))
    if hout not in (None, 0, wintypes.HANDLE(-1).value):
        mode = wintypes.DWORD()
        if k32.GetConsoleMode(hout, ctypes.byref(mode)):
            _log("stdout 已是控制台句柄")
            _flush(True)
            return True
    _log(f"stdout 非控制台句柄 ({hout})")

    # 2) 沿祖先链附加：跳过无控制台的 GUI 引导器，找到宿主终端
    STD_INPUT_HANDLE, STD_ERROR_HANDLE = -10, -12  # pylint: disable=invalid-name
    GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000  # pylint: disable=invalid-name
    FILE_SHARE_READ, FILE_SHARE_WRITE = 1, 2  # pylint: disable=invalid-name
    OPEN_EXISTING = 3  # pylint: disable=invalid-name
    ERROR_ACCESS_DENIED = 5  # pylint: disable=invalid-name

    k32.AttachConsole.restype = wintypes.BOOL
    k32.CreateFileW.restype = wintypes.HANDLE

    attached = None
    already_console = False
    for pid, name in _ancestor_chain(k32):
        k32.AttachConsole.argtypes = [wintypes.DWORD]
        if k32.AttachConsole(wintypes.DWORD(pid)):
            attached = (pid, name)
            _log(f"AttachConsole 成功: {name}({pid})")
            break
        err = k32.GetLastError()
        if err == ERROR_ACCESS_DENIED:
            # 本进程已带控制台（ConPTY 下 GetConsoleWindow 不可用，以此兜底）
            already_console = True
            _log(f"已有控制台（ACCESS_DENIED @ {name}({pid})）")
            break
        _log(f"跳过 {name}({pid}) err={err}")

    if attached is None and not already_console:
        _log("祖先链无可附加控制台")
        _flush(False)
        return False

    # 3) 接好标准句柄：Win32 槽位（Textual 输入线程走 GetStdHandle）+ Python 流
    conout = k32.CreateFileW("CONOUT$", GENERIC_WRITE | GENERIC_READ,
                             FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                             OPEN_EXISTING, 0, None)
    conin = k32.CreateFileW("CONIN$", GENERIC_READ | GENERIC_WRITE,
                            FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                            OPEN_EXISTING, 0, None)
    if conout in (None, 0, wintypes.HANDLE(-1).value) or \
            conin in (None, 0, wintypes.HANDLE(-1).value):
        _log(f"CreateFileW 控制台设备失败 out={conout} in={conin}")
        _flush(False)
        return False
    k32.SetStdHandle(wintypes.DWORD(STD_OUTPUT_HANDLE), conout)
    k32.SetStdHandle(wintypes.DWORD(STD_ERROR_HANDLE), conout)
    k32.SetStdHandle(wintypes.DWORD(STD_INPUT_HANDLE), conin)
    try:
        out_f = open("CONOUT$", "w", encoding="utf-8")
        err_f = open("CONOUT$", "w", encoding="utf-8")
        in_f = open("CONIN$", "r", encoding="utf-8")
    except OSError as exc:
        _log(f"重绑定标准流出错: {exc}")
        _flush(False)
        return False
    sys.stdout = out_f
    sys.stderr = err_f
    sys.stdin = in_f
    # Textual Windows 驱动读 sys.__stdout__/__stderr__（而非 sys.stdout），
    # enable_application_mode() 还会立即对 sys.__stdin__ 查询控制台模式——
    # 三者都要接好，缺 __stdin__ 会在驱动启动时 AttributeError（v0.5.1 修复）
    sys.__stdout__ = out_f
    sys.__stderr__ = err_f
    sys.__stdin__ = in_f
    global _TUI_ATTACHED
    _TUI_ATTACHED = True
    _flush(True)
    return True


def _ancestor_chain(k32, max_levels: int = 10):
    """当前进程的祖先链 [(pid, 进程名), …]，从直接父进程开始。"""
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x2  # pylint: disable=invalid-name

    class _PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (None, 0, wintypes.HANDLE(-1).value):
        return []
    table = {}
    pe = _PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(_PROCESSENTRY32)
    ok = k32.Process32First(snap, ctypes.byref(pe))
    while ok:
        table[pe.th32ProcessID] = (
            pe.th32ParentProcessID,
            pe.szExeFile.decode(errors="replace"))
        ok = k32.Process32Next(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)

    pid = k32.GetCurrentProcessId()
    chain_pids = []
    for _ in range(max_levels):
        if pid not in table:
            break
        chain_pids.append(pid)
        pid = table[pid][0]
    # 排除自身，pid 与进程名一一对应（日志显示用）
    return [(p, table[p][1]) for p in chain_pids[1:]]


def _clean_child_env_for_frozen() -> None:
    """剥离子进程继承的 PyInstaller 运行时库路径（Linux/onefile，v0.5.4）。

    PyInstaller onefile 引导器会设置 LD_LIBRARY_PATH 指向运行时解包目录
    _MEIxxx 并被所有子进程继承。旧工具链（如 ubuntu-22.04）构建出的包在该
    目录带有旧版 libstdc++.so.6——系统 ffmpeg 等动态链接程序会因
    "GLIBCXX_3.4.32 not found" 拒绝启动，导致 AppImage 下 ffbin 自动切换
    系统 ffmpeg 失败、硬件编码探测全军覆没。应用自身的库在启动时已完成
    映射，这里只从环境变量里剥掉指向 _MEIPASS 的条目（保留其他路径），
    影响范围仅限之后拉起的子进程。
    """
    if os.name != "nt" and getattr(sys, "frozen", False) \
            and getattr(sys, "_MEIPASS", None):
        mei = os.path.abspath(sys._MEIPASS)
        for var in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
            val = os.environ.get(var)
            if not val:
                continue
            kept = []
            for p in val.split(":"):
                ap = os.path.abspath(p) if p else ""
                if ap and (ap == mei or ap.startswith(mei + os.sep)):
                    continue
                kept.append(p)
            if kept:
                os.environ[var] = ":".join(kept)
            else:
                os.environ.pop(var, None)


def main() -> int:
    _clean_child_env_for_frozen()
    from PySide6.QtWidgets import QApplication

    # TUI 交互模式：GUI 子系统 exe 需先附加控制台；不可用时降级提示
    if "--tui" in sys.argv:
        if not _setup_tui_console():
            try:
                from PySide6.QtWidgets import QMessageBox

                a = QApplication([])
                QMessageBox.warning(
                    None, "TUI 模式",
                    "TUI 模式需要从终端启动：\n\n"
                    "  在命令行中运行  VideoWatermark.exe --tui\n\n"
                    "（双击启动无法显示终端界面，请改用 GUI 或从终端运行）")
            except Exception:  # noqa: BLE001
                pass
            return 2
        sys.argv.remove("--tui")
        # 直接运行 GUI exe --tui 时 shell 不等待、会与 TUI 抢键盘（v0.5.2）：
        # 非"垫片拉起"的附加启动打印提示，引导使用 VideoWatermarkTUI.exe
        if _TUI_ATTACHED and not os.environ.get("VIDEO_WATERMARK_TUI_PARENT_SHIM"):
            try:
                print("提示：cmd/PowerShell 不等待 GUI 程序、会与 TUI 抢键盘——"
                      "若按键无响应，请改用同目录的 VideoWatermarkTUI.exe 启动，"
                      "或在 cmd 中用 start /wait 运行。")
                sys.stdout.flush()
            except Exception:  # noqa: BLE001
                pass
        from app.tui import main as tui_main
        return tui_main(sys.argv[1:])

    # 自检模式：离屏构建主窗口 + 端到端编码验证（打包完整性）
    if "--selftest" in sys.argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import shutil
        import tempfile

        from PySide6.QtWidgets import QApplication

        app = QApplication([])
        win = MainWindow()
        ok = win.windowTitle() == "视频水印工具"

        # 1) 内置 ffmpeg 二进制可用（打包完整性独立验证，与 ffbin 解析无关）
        from app.core import ffbin

        ffmpeg_exe = ffbin.bundled_exe()
        ok = ok and os.path.isfile(ffmpeg_exe)
        # 实际使用的 ffmpeg（可能是内置，也可能是显式/自动选定的系统 ffmpeg）
        resolved = ffbin.get_ffmpeg_exe()

        # 2) 端到端：用内置 ffmpeg 生成短视频 -> 加水印 -> 编码输出
        from app.core.encoder import generate_sample_video, process
        from app.models import KIND_TEXT, MODE_TILED, WatermarkConfig

        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(tmp, "t.mp4")
            out = os.path.join(tmp, "o.mp4")
            generate_sample_video(src, size=(160, 90), duration=0.5, fps=15)
            process(src, out, WatermarkConfig(
                kind=KIND_TEXT, mode=MODE_TILED, text="SELFTEST"))
            ok = ok and os.path.isfile(out) and os.path.getsize(out) > 1000
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # 3) 批量并行用到的进程池在打包环境下可用：
        #    freeze_support() 保证子进程不重新弹主窗口、正常执行 worker。
        #    若缺 freeze_support，子进程会弹窗阻塞，pool.submit 失败/超时 -> 自检失败。
        import concurrent.futures

        with concurrent.futures.ProcessPoolExecutor(max_workers=1) as pool:
            ok = ok and pool.submit(_selftest_double, 21).result(timeout=60) == 42

        print(f"SELFTEST_OK ffmpeg={resolved} (bundled={ffmpeg_exe})"
              if ok else "SELFTEST_FAIL", flush=True)
        return 0 if ok else 1

    app = QApplication(sys.argv)
    app.setApplicationName("视频水印工具")

    # 应用已保存的 ffmpeg 二进制设置（QSettings 依赖 QApplication，故在其后）
    # 须在 ffbin 首次解析之前完成，否则设置不生效
    from app.ui.main_window import apply_ffmpeg_setting_to_env, load_ffmpeg_setting
    _mode, _path = load_ffmpeg_setting()
    apply_ffmpeg_setting_to_env(_mode, _path)

    # 提前解析 ffmpeg 二进制（Linux 自动切换 / 显式指定），避免首个任务时才决策
    from app.core import ffbin
    ffbin.get_ffmpeg_exe()

    _apply_app_icon(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    # 打包（PyInstaller onefile）后，批量并行用 ProcessPoolExecutor 拉起的
    # 子进程会重新执行本入口；必须在此调用 freeze_support()，否则子进程
    # 会重复执行 main() 弹出新主窗口而不会真正跑 worker。
    # 开发模式（python -m app.main）下该调用是无副作用 no-op。
    import multiprocessing
    multiprocessing.freeze_support()

    # 启动失败时把错误写入 gui_error.log（pythonw 静默启动时也能排查）
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        import traceback
        log_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "gui_error.log")
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        print(f"启动失败，详情见 {log_path}", file=sys.stderr)
        sys.exit(1)
