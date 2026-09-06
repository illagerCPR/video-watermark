# PyInstaller 打包配置：生成独立 VideoWatermark.exe（单文件、无控制台窗口）
#
# 构建：  .venv\Scripts\pyinstaller.exe video_watermark.spec --noconfirm
# 产物：  dist\VideoWatermark.exe
#         dist\VideoWatermarkTUI.exe（仅 Windows：TUI 控制台垫片，见 app/tui_shim.py）
# 自检：  VideoWatermark.exe --selftest   （离屏构建主窗口，退出码 0 = 正常）
import sys

from PyInstaller.utils.hooks import collect_data_files

# 打包 imageio-ffmpeg 内置的静态 ffmpeg 二进制（binaries\ffmpeg-*.exe），保证离线可用
# 同时内嵌 icon.ico：既用于 exe 文件图标，也供运行时 setWindowIcon 读取（任务栏/标题栏图标）
datas = collect_data_files("imageio_ffmpeg") + [("icon.ico", ".")]

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VideoWatermark",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # 无控制台窗口（GUI 程序）
    disable_windowed_traceback=False,
    icon="icon.ico",
)

if sys.platform == "win32":
    # TUI 垫片（控制台子系统，v0.5.2）：cmd/PowerShell 只等待控制台程序；
    # GUI 主程序 --tui 直接运行时 shell 继续读控制台输入、与 TUI 抢键。
    # 垫片无 Qt/ffmpeg 依赖，体积小；与主程序同目录分发。
    a_shim = Analysis(
        ["app/tui_shim.py"],
        pathex=["."],
        binaries=[],
        datas=[],
        hiddenimports=[],
        hookspath=[],
        runtime_hooks=[],
        excludes=[],
        noarchive=False,
    )

    pyz_shim = PYZ(a_shim.pure)

    exe_tui = EXE(
        pyz_shim,
        a_shim.scripts,
        a_shim.binaries,
        a_shim.datas,
        [],
        name="VideoWatermarkTUI",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,             # 控制台子系统：shell 会等待它，TUI 独占键盘
        disable_windowed_traceback=False,
        icon="icon.ico",
    )
