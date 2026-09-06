#!/usr/bin/env bash
# 视频水印工具 - Linux/macOS 启动器（对齐 启动.bat 的行为）
# 首次运行自动创建虚拟环境并安装依赖，之后直接启动 GUI。
set -u
cd "$(dirname "$0")"

VENV=.venv
PY=python3

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "[启动] 未找到 python3，请先安装 Python 3.10+。" >&2
    exit 1
fi

# 1) 虚拟环境（缺 ensurepip 的系统回退到 --without-pip + get-pip 引导）
if [ ! -x "$VENV/bin/python" ]; then
    echo "[启动] 未找到虚拟环境，正在用 $PY 创建..."
    if ! "$PY" -m venv "$VENV" 2>/dev/null; then
        echo "[启动] 系统缺 ensurepip，改用 get-pip.py 引导..."
        "$PY" -m venv --without-pip "$VENV"
        curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py \
            || wget -qO /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
        "$VENV/bin/python" /tmp/get-pip.py
    fi
fi

# 2) 依赖（官方源失败自动换清华镜像）
if ! "$VENV/bin/python" -c "import PIL, imageio_ffmpeg, PySide6" >/dev/null 2>&1; then
    echo "[启动] 正在安装依赖（requirements.txt）..."
    "$VENV/bin/pip" install -r requirements.txt \
        || "$VENV/bin/pip" install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
fi

# 3) 启动 GUI；失败时给出 Linux 常见缺库提示
echo "[启动] 视频水印工具"
code=0
"$VENV/bin/python" -m app.main "$@" || code=$?
if [ "$code" -ne 0 ]; then
    echo ""
    echo "[提示] 若报 “could not load the Qt platform plugin xcb”，是缺系统图形库，"
    echo "  Debian/Ubuntu:  sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1"
    echo "  Fedora:         sudo dnf install xcb-util-cursor libxkbcommon-x11 libglvnd-egl"
    echo "  无显示环境可离屏运行（仅自检/CLI）：QT_QPA_PLATFORM=offscreen $0"
fi
exit "$code"
