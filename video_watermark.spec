# PyInstaller 打包配置：生成独立 VideoWatermark.exe（单文件、无控制台窗口）
#
# 构建：  .venv\Scripts\pyinstaller.exe video_watermark.spec --noconfirm
# 产物：  dist\VideoWatermark.exe
# 自检：  VideoWatermark.exe --selftest   （离屏构建主窗口，退出码 0 = 正常）
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
