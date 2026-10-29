"""Ícone do app desenhado em código, para não depender de arquivos: o visor com o ponto de sinal."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from klick import theme


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw(size))
    return icon


def _draw(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.G900))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.16, size * 0.16)
    if size >= 32:
        p.setPen(QPen(QColor(theme.G700), size / 64 * 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        inset = size / 64 * 0.75
        p.drawRoundedRect(QRectF(inset, inset, size - 2 * inset, size - 2 * inset), size * 0.145, size * 0.145)

    # Cantos do visor: em ícones pequenos ficam mais grossos e mais perto da borda para não sumir.
    small = size <= 24
    pen = QPen(QColor(theme.PAPER), size / (9 if small else 12.8))
    pen.setCapStyle(Qt.PenCapStyle.SquareCap)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    m, arm = size * (0.2 if small else 0.234), size * (0.2 if small else 0.172)
    lo, hi = m, size - m
    for x, dx in ((lo, arm), (hi, -arm)):
        for y, dy in ((lo, arm), (hi, -arm)):
            p.drawPolyline([QPointF(x + dx, y), QPointF(x, y), QPointF(x, y + dy)])

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.S500))
    r = size * (0.12 if small else 0.094)
    p.drawEllipse(QPointF(size / 2, size / 2), r, r)
    p.end()
    return pixmap
