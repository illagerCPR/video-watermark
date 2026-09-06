#!/usr/bin/env bash
# 把 PyInstaller onefile 产物打包为 AppImage（Linux 用）。
# 前置：dist/VideoWatermark 已由 pyinstaller 生成；仓库根目录有 icon.ico。
# 需要：python（Pillow，用于 ico→png）、curl、appimagetool（自动下载，
#       无 FUSE 环境自动以 APPIMAGE_EXTRACT_AND_RUN=1 运行）。
# 产物：VideoWatermark-linux-x86_64.AppImage
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python

APPNAME=VideoWatermark
APPDIR=AppDir

[ -f "dist/$APPNAME" ] || { echo "缺 dist/$APPNAME，请先 pyinstaller 构建"; exit 1; }

# 1) AppDir 骨架
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp "dist/$APPNAME" "$APPDIR/usr/bin/"
chmod +x "$APPDIR/usr/bin/$APPNAME"

# 2) AppRun：定位自身目录后 exec 主程序
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/VideoWatermark" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# 3) desktop 条目
cat > "$APPDIR/video-watermark.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=VideoWatermark
Comment=桌面视频水印工具（平铺/移动水印）
Exec=VideoWatermark
Icon=video-watermark
Categories=AudioVideo;Video;
Terminal=false
EOF

# 4) 图标：icon.ico → png（取最大尺寸）
"$PY" - <<'EOF'
from PIL import Image
im = Image.open("icon.ico")
best = im
try:
    sizes = getattr(im, "ico", None) and im.ico.sizes() or None
    if sizes:
        best = Image.open("icon.ico"); best.size = max(sizes)
except Exception:
    pass
best.save("AppDir/video-watermark.png")
EOF

# 5) appimagetool 打包（无 FUSE 时用自动解包运行）
TOOL=build/appimagetool-x86_64.AppImage
mkdir -p build
if [ ! -f "$TOOL" ]; then
    curl -fsSL -o "$TOOL" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
fi
chmod +x "$TOOL"
export APPIMAGE_EXTRACT_AND_RUN=1
"$TOOL" "$APPDIR" "$APPNAME-linux-x86_64.AppImage"

echo "产物: $APPNAME-linux-x86_64.AppImage"
