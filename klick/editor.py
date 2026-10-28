"""Editor do print: anotações (seta, retângulo, texto, numeração) e pixelar.

As anotações ficam numa lista de formas sobre a imagem original, em pixels da
imagem; nada é "queimado" até o render final, então o desfazer é só um pop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QKeySequence, QPainter,
                           QPainterPath, QPen, QPolygonF, QShortcut)
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QInputDialog, QScrollArea, QToolButton, QVBoxLayout, QWidget)

from klick.actions import Action
from klick.icon import app_icon

COLORS = ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#111827", "#ffffff"]
MIN_SHAPE = 4  # px de imagem; menor que isso é clique perdido


class Tool(str, Enum):
    ARROW = "arrow"
    RECT = "rect"
    TEXT = "text"
    NUMBER = "number"
    PIXELATE = "pixelate"


@dataclass
class Style:
    color: QColor
    scale: float  # pixels de imagem por pixel lógico; mantém a espessura igual em telas HiDPI

    @property
    def width(self) -> float:
        return 3 * self.scale


@dataclass
class Arrow:
    start: QPointF
    end: QPointF
    style: Style

    def paint(self, p: QPainter, base: QImage) -> None:
        w = self.style.width
        length = math.hypot(self.end.x() - self.start.x(), self.end.y() - self.start.y())
        if length < 1:
            return
        head = min(w * 5, length * 0.6)
        angle = math.atan2(self.end.y() - self.start.y(), self.end.x() - self.start.x())
        neck = QPointF(self.end.x() - head * 0.8 * math.cos(angle), self.end.y() - head * 0.8 * math.sin(angle))
        pen = QPen(self.style.color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(self.start, neck)
        wing = math.radians(25)
        points = [
            self.end,
            QPointF(self.end.x() - head * math.cos(angle - wing), self.end.y() - head * math.sin(angle - wing)),
            QPointF(self.end.x() - head * math.cos(angle + wing), self.end.y() - head * math.sin(angle + wing)),
        ]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.style.color)
        p.drawPolygon(QPolygonF(points))

    def valid(self) -> bool:
        return math.hypot(self.end.x() - self.start.x(), self.end.y() - self.start.y()) >= MIN_SHAPE


@dataclass
class Box:
    rect: QRectF
    style: Style

    def paint(self, p: QPainter, base: QImage) -> None:
        pen = QPen(self.style.color, self.style.width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect.normalized())

    def valid(self) -> bool:
        r = self.rect.normalized()
        return r.width() >= MIN_SHAPE and r.height() >= MIN_SHAPE


@dataclass
class Text:
    pos: QPointF
    text: str
    style: Style

    def paint(self, p: QPainter, base: QImage) -> None:
        font = QFont()
        font.setPixelSize(round(18 * self.style.scale))
        font.setBold(True)
        path = QPainterPath()
        path.addText(self.pos, font, self.text)
        # Contorno claro/escuro para o texto ler em qualquer fundo.
        halo = QColor("#111827") if self.style.color.lightness() > 160 else QColor("white")
        p.setPen(QPen(halo, 3 * self.style.scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.style.color)
        p.drawPath(path)

    def valid(self) -> bool:
        return bool(self.text.strip())


@dataclass
class Number:
    center: QPointF
    value: int
    style: Style

    def paint(self, p: QPainter, base: QImage) -> None:
        radius = 13 * self.style.scale
        p.setPen(QPen(QColor("white"), 2 * self.style.scale))
        p.setBrush(self.style.color)
        p.drawEllipse(self.center, radius, radius)
        font = QFont()
        font.setPixelSize(round(15 * self.style.scale))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#111827") if self.style.color.lightness() > 160 else QColor("white"))
        p.drawText(QRectF(self.center.x() - radius, self.center.y() - radius, radius * 2, radius * 2),
                   Qt.AlignmentFlag.AlignCenter, str(self.value))

    def valid(self) -> bool:
        return True


@dataclass
class Pixelate:
    rect: QRectF
    style: Style

    def block(self, region: QRect) -> int:
        # Blocos grandes o bastante para não dar para "despixelar" uma linha de texto.
        return max(round(10 * self.style.scale), min(region.width(), region.height()) // 3, 2)

    def paint(self, p: QPainter, base: QImage) -> None:
        region = self.rect.normalized().toAlignedRect().intersected(base.rect())
        if region.isEmpty():
            return
        block = self.block(region)
        small = base.copy(region).scaled(max(1, region.width() // block), max(1, region.height() // block),
                                         Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawImage(QRectF(region), small)
        p.restore()

    def valid(self) -> bool:
        r = self.rect.normalized()
        return r.width() >= MIN_SHAPE and r.height() >= MIN_SHAPE


def render(base: QImage, shapes: list) -> QImage:
    image = base.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    for shape in shapes:
        shape.paint(p, base)
    p.end()
    return image.convertToFormat(QImage.Format.Format_RGB32)


class Canvas(QWidget):
    changed = Signal()

    def __init__(self, image: QImage, image_scale: float, view_scale: float):
        super().__init__()
        self.base = image
        self.shapes: list = []
        self.tool = Tool.ARROW
        self.color = QColor(COLORS[0])
        self._image_scale = image_scale  # px de imagem por px lógico da tela de origem
        self._view = view_scale  # px de widget por px de imagem
        self._draft = None
        self._next_number = 1
        self.setFixedSize(QSize(round(image.width() * view_scale), round(image.height() * view_scale)))
        self.setCursor(Qt.CursorShape.CrossCursor)

    @property
    def next_number(self) -> int:
        return self._next_number

    def undo(self) -> None:
        if not self.shapes:
            return
        shape = self.shapes.pop()
        if isinstance(shape, Number):
            self._next_number = shape.value
        self.update()
        self.changed.emit()

    def result(self) -> QImage:
        return render(self.base, self.shapes)

    def add(self, shape) -> None:
        if shape.valid():
            self.shapes.append(shape)
            if isinstance(shape, Number):
                self._next_number = shape.value + 1
            self.update()
            self.changed.emit()

    def _style(self) -> Style:
        return Style(QColor(self.color), self._image_scale)

    def _to_image(self, pos: QPointF) -> QPointF:
        return QPointF(pos.x() / self._view, pos.y() / self._view)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = self._to_image(event.position())
        if self.tool is Tool.ARROW:
            self._draft = Arrow(pos, pos, self._style())
        elif self.tool is Tool.RECT:
            self._draft = Box(QRectF(pos, pos), self._style())
        elif self.tool is Tool.PIXELATE:
            self._draft = Pixelate(QRectF(pos, pos), self._style())
        elif self.tool is Tool.NUMBER:
            self.add(Number(pos, self._next_number, self._style()))
        elif self.tool is Tool.TEXT:
            text, ok = QInputDialog.getText(self, "Texto", "Texto da anotação:")
            if ok:
                self.add(Text(pos, text, self._style()))

    def mouseMoveEvent(self, event) -> None:
        if self._draft is None:
            return
        pos = self._to_image(event.position())
        if isinstance(self._draft, Arrow):
            self._draft.end = pos
        else:
            self._draft.rect.setBottomRight(pos)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._draft is None:
            return
        draft, self._draft = self._draft, None
        self.add(draft)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(self._view, self._view)
        p.drawImage(0, 0, self.base)
        for shape in [*self.shapes, *([self._draft] if self._draft else [])]:
            shape.paint(p, self.base)


EDITOR_STYLE = """
QWidget#editor { background: #111827; }
QFrame#bar { background: #1f2937; border-bottom: 1px solid #374151; }
QToolButton { color: #f9fafb; background: transparent; border: 1px solid transparent; padding: 5px 9px;
              border-radius: 4px; }
QToolButton:hover { background: #374151; }
QToolButton:checked { background: #374151; border-color: #3b82f6; }
QToolButton:disabled { color: #6b7280; }
QScrollArea { border: none; background: #111827; }
"""

TOOLS = [
    (Tool.ARROW, "Seta", "A"),
    (Tool.RECT, "Retângulo", "R"),
    (Tool.TEXT, "Texto", "T"),
    (Tool.NUMBER, "Número", "N"),
    (Tool.PIXELATE, "Pixelar", "P"),
]


class EditorWindow(QWidget):
    done = Signal(object, QImage)  # Action.COPY ou Action.SAVE, imagem final

    def __init__(self, image: QImage, image_scale: float = 1.0):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("editor")
        self.setWindowTitle("Klick: editar captura")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(EDITOR_STYLE)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        view = min(1 / image_scale, screen.width() * 0.85 / image.width(), (screen.height() * 0.8) / image.height())
        self.canvas = Canvas(image, image_scale, view)
        self.canvas.changed.connect(self._update_undo)

        bar = QFrame(objectName="bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(4)

        self._tools = QButtonGroup(self)
        self._tools.setExclusive(True)
        for tool, label, key in TOOLS:
            button = self._button(row, label, f"{label} ({key})", lambda _=False, t=tool: self.set_tool(t))
            button.setCheckable(True)
            button.setChecked(tool is Tool.ARROW)
            button.setProperty("tool", tool.value)
            self._tools.addButton(button)
            QShortcut(QKeySequence(key), self, activated=lambda t=tool: self.set_tool(t))

        row.addSpacing(12)
        self._swatches = QButtonGroup(self)
        for color in COLORS:
            swatch = QToolButton()
            swatch.setCheckable(True)
            swatch.setChecked(color == COLORS[0])
            swatch.setFixedSize(22, 22)
            swatch.setToolTip(f"Cor {color}")
            swatch.setAccessibleName(f"Cor {color}")
            swatch.setStyleSheet(f"QToolButton {{ background: {color}; border: 2px solid #4b5563; padding: 0; }}"
                                 f"QToolButton:checked {{ border: 2px solid #f9fafb; }}")
            swatch.clicked.connect(lambda _=False, c=color: self.set_color(c))
            self._swatches.addButton(swatch)
            row.addWidget(swatch)

        row.addSpacing(12)
        self._undo = self._button(row, "Desfazer", "Desfazer (Ctrl+Z)", self.canvas.undo)
        self._undo.setEnabled(False)
        row.addStretch(1)
        self._button(row, "Copiar", "Copiar e fechar (Ctrl+C)", lambda: self._finish(Action.COPY))
        self._button(row, "Salvar", "Salvar e fechar (Ctrl+S)", lambda: self._finish(Action.SAVE))

        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.canvas.undo)
        QShortcut(QKeySequence.StandardKey.Copy, self, activated=lambda: self._finish(Action.COPY))
        QShortcut(QKeySequence.StandardKey.Save, self, activated=lambda: self._finish(Action.SAVE))
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar)
        layout.addWidget(scroll, 1)

        bar_width = bar.sizeHint().width()
        self.resize(max(bar_width, self.canvas.width() + 24), bar.sizeHint().height() + self.canvas.height() + 24)

    def set_tool(self, tool: Tool) -> None:
        self.canvas.tool = tool
        for button in self._tools.buttons():
            button.setChecked(button.property("tool") == tool.value)

    def set_color(self, color: str) -> None:
        self.canvas.color = QColor(color)

    def _update_undo(self) -> None:
        self._undo.setEnabled(bool(self.canvas.shapes))

    def _finish(self, action: Action) -> None:
        self.done.emit(action, self.canvas.result())
        self.close()

    @staticmethod
    def _button(row: QHBoxLayout, text: str, tip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.clicked.connect(slot)
        row.addWidget(button)
        return button
