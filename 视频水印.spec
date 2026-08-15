# PyInstaller 打包配置：生成独立 视频水印.exe（单文件、无控制台窗口）
#
# 构建：  .venv\Scripts\pyinstaller.exe 视频水印.spec --noconfirm
# 产物：  dist\视频水印.exe
# 自检：  视频水印.exe --selftest   （离屏构建主窗口，退出码 0 = 正常）
from PyInstaller.utils.hooks import collect_data_files

# 打包 imageio-ffmpeg 内置的静态 ffmpeg 二进制（binaries\ffmpeg-*.exe），保证离线可用
datas = collect_data_files("imageio_ffmpeg")

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
    name="视频水印",
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
