# -*- coding: utf-8 -*-
"""将 ico.svg 渲染为多尺寸 icon.ico（16/24/32/48/64/128/256）。

原理：
  - PySide6.QtSvg.QSvgRenderer 离屏渲染 SVG 到透明画布（保持宽高比、居中）
  - Pillow 将大图缩放为多个尺寸后写入标准 .ico 容器
用法：
  .venv\\Scripts\\python.exe scripts\\svg_to_ico.py ico.svg icon.ico
"""
import io
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from PIL import Image

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def svg_to_ico(svg_path: str, ico_path: str, canvas: int = 256) -> None:
    app = QApplication.instance() or QApplication([])
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise RuntimeError(f"无法解析 SVG：{svg_path}")

    # 保持宽高比，缩放到 canvas 内并居中（四周留透明边）
    vb = renderer.viewBoxF()
    scale = min(canvas / vb.width(), canvas / vb.height())
    w, h = vb.width() * scale, vb.height() * scale
    x, y = (canvas - w) / 2, (canvas - h) / 2

    img = QImage(canvas, canvas, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(p, QRectF(x, y, w, h))
    p.end()

    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.ReadWrite)
    img.save(buf, "PNG")
    png_bytes = bytes(buf.data())
    buf.close()

    base = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    # 生成多尺寸：Pillow 会自动按 sizes 缩放基础图写入 ICO 容器
    base.save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
    )
    app.processEvents()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        svg_path = os.path.join(root, "ico.svg")
        ico_path = os.path.join(root, "icon.ico")
    else:
        svg_path, ico_path = sys.argv[1], sys.argv[2]
    svg_to_ico(svg_path, ico_path)
    print(f"已生成 {ico_path}（含尺寸 {ICO_SIZES}）")
