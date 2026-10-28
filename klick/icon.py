"""Ícone do app desenhado em código, para não depender de arquivos."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128):
        icon.addPixmap(_draw(size))
    return icon


def _draw(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#3b82f6"))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)

    # Cantos de um retângulo de seleção.
    pen = QPen(QColor("white"), max(1.5, size / 12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    m, arm = size * 0.25, size * 0.18
    lo, hi = m, size - m
    for x, dx in ((lo, arm), (hi, -arm)):
        for y, dy in ((lo, arm), (hi, -arm)):
            p.drawLine(int(x), int(y), int(x + dx), int(y))
            p.drawLine(int(x), int(y), int(x), int(y + dy))
    p.end()
    return pixmap
