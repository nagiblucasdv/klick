"""Marcação do print: ferramentas para evidenciar (destaque, marca-texto, seta, passos, texto)
e para analisar (lupa, ocultar, medir, conta-gotas).

As marcações ficam numa lista de formas sobre a imagem original, em pixels da imagem;
nada é "queimado" até o render final, então desfazer é só um pop. O mesmo `Marker`
serve à marcação dentro da própria captura (overlay) e à janela de marcar da galeria.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFontMetricsF, QGuiApplication, QImage, QKeySequence, QPainter, QPainterPath,
                           QPen, QPolygonF, QShortcut)
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

from klick import icons, theme
from klick.actions import Action
from klick.icon import app_icon
from klick.widgets import Segmented, button, icon_button

# Cores de anotação: sinal, REC, foco, ciano, alumínio e grafite.
PALETTE = [theme.S500, theme.REC, theme.OK, theme.CYAN, theme.PAPER, theme.G900]
PALETTE_NAMES = ["Laranja", "Vermelho", "Verde", "Ciano", "Branco", "Grafite"]
SIZES = [("thin", "Fina", 0.66), ("medium", "Média", 1.0), ("thick", "Grossa", 1.6)]
MIN_SHAPE = 4  # px de imagem; menor que isso é clique perdido
SNAP_DEGREES = 4  # a régua gruda na horizontal/vertical perto disso


class Tool(str, Enum):
    SPOT = "spot"
    HIGHLIGHT = "highlight"
    ARROW = "arrow"
    STEP = "step"
    TEXT = "text"
    LOUPE = "loupe"
    HIDE = "hide"
    MEASURE = "measure"
    PICK = "pick"


# (ferramenta, ícone, nome, tecla); None separa grupos: destacar | analisar
TOOLS = [
    (Tool.SPOT, "spot", "Destaque", "D"),
    (Tool.HIGHLIGHT, "mark", "Marca-texto", "M"),
    (Tool.ARROW, "arrow", "Seta", "A"),
    (Tool.STEP, "step", "Passo", "N"),
    (Tool.TEXT, "text", "Texto", "T"),
    None,
    (Tool.LOUPE, "loupe", "Lupa", "L"),
    (Tool.HIDE, "hide", "Ocultar", "P"),
    (Tool.MEASURE, "ruler", "Medir", "R"),
    (Tool.PICK, "drop", "Conta-gotas", "I"),
]
KEYS = {Qt.Key(ord(key)): tool for entry in TOOLS if entry for tool, _, _, key in [entry]}
# O que cada ferramenta faz, mostrado embaixo da lista.
DESCRIPTIONS = {
    Tool.SPOT: "Arraste uma área: o resto do print escurece.",
    Tool.HIGHLIGHT: "Pinta por cima como caneta marca-texto.",
    Tool.ARROW: "Arraste do ponto de partida até o alvo.",
    Tool.STEP: "Clique para numerar: 1, 2, 3… Bom para tutorial.",
    Tool.TEXT: "Clique e digite uma nota. Enter termina.",
    Tool.LOUPE: "Arraste do detalhe até onde a lupa deve ficar.",
    Tool.HIDE: "Pixela dados sensíveis, como CPF e senhas.",
    Tool.MEASURE: "Mede a distância em pixels. Gruda na reta.",
    Tool.PICK: "Clique num ponto para copiar a cor (#hex).",
}
TABS = [("evidence", "Destacar"), ("analysis", "Analisar")]
TOOL_TAB = {tool: ("analysis" if i > TOOLS.index(None) else "evidence")
            for i, entry in enumerate(TOOLS) if entry for tool in [entry[0]]}


@dataclass
class Style:
    color: QColor
    scale: float  # pixels de imagem por pixel lógico; mantém a espessura igual em telas HiDPI
    size: float = 1.0  # espessura escolhida: fina, média ou grossa

    @property
    def unit(self) -> float:
        return self.scale * self.size

    @property
    def width(self) -> float:
        return 3 * self.unit


def _ink(color: QColor) -> QColor:
    """Cor de texto que lê sobre `color`."""
    return QColor(theme.G950) if color.lightness() > 140 else QColor("#ffffff")


@dataclass
class Spotlight:
    """Destaque: escurece o resto do print. Vários destaques escurecem uma vez só (ver render)."""
    rect: QRectF
    style: Style

    def paint(self, p: QPainter, base: QImage) -> None:
        paint_spotlights(p, base, [self])

    def valid(self) -> bool:
        r = self.rect.normalized()
        return r.width() >= MIN_SHAPE and r.height() >= MIN_SHAPE


@dataclass
class Highlight:
    rect: QRectF
    style: Style

    def paint(self, p: QPainter, base: QImage) -> None:
        color = QColor(self.style.color)
        color.setAlpha(150)
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(self.rect.normalized(), 2 * self.style.scale, 2 * self.style.scale)
        p.restore()

    def valid(self) -> bool:
        r = self.rect.normalized()
        return r.width() >= MIN_SHAPE and r.height() >= MIN_SHAPE


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
        # Contorno escuro fino por baixo: a seta lê em fundo claro e escuro.
        p.setPen(QPen(QColor(18, 17, 16, 110), w + 2 * self.style.scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(self.start, neck)
        p.setPen(QPen(self.style.color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
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
class Step:
    """Passo numerado (1, 2, 3) para tutorial."""
    center: QPointF
    value: int
    style: Style

    def paint(self, p: QPainter, base: QImage) -> None:
        s = self.style.unit
        side = 26 * s
        box = QRectF(self.center.x() - side / 2, self.center.y() - side / 2, side, side)
        p.setPen(QPen(QColor(theme.G950), 2 * s))
        p.setBrush(self.style.color)
        p.drawRoundedRect(box, 3 * s, 3 * s)
        p.setFont(theme.font(15 * s, 700, mono=True))
        p.setPen(_ink(self.style.color))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, str(self.value))

    def valid(self) -> bool:
        return True


@dataclass
class Note:
    """Nota de texto: etiqueta grafite com a barra da cor. Digitada direto, sem diálogo."""
    pos: QPointF
    text: str
    style: Style
    editing: bool = False

    def box(self) -> QRectF:
        s = self.style.unit
        metrics = QFontMetricsF(theme.font(14 * s, 500))
        width = max(metrics.horizontalAdvance(self.text or "Digite"), 40 * s)
        return QRectF(self.pos.x(), self.pos.y(), width + 22 * s, metrics.height() + 12 * s)

    def paint(self, p: QPainter, base: QImage) -> None:
        s = self.style.unit
        box = self.box()
        p.setPen(QPen(QColor(theme.G700), 1 * s))
        p.setBrush(QColor(theme.G900))
        p.drawRoundedRect(box, 3 * s, 3 * s)
        p.fillRect(QRectF(box.left(), box.top(), 4 * s, box.height()), self.style.color)
        p.setFont(theme.font(14 * s, 500))
        text_box = box.adjusted(12 * s, 0, -8 * s, 0)
        if self.text:
            p.setPen(QColor(theme.PAPER))
            p.drawText(text_box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text)
        elif self.editing:
            p.setPen(QColor(theme.G400))
            p.drawText(text_box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Digite")
        if self.editing:
            x = text_box.left() + QFontMetricsF(theme.font(14 * s, 500)).horizontalAdvance(self.text) + 1 * s
            p.setPen(QPen(QColor(theme.S500), 1.5 * s))
            p.drawLine(QPointF(x, box.top() + 5 * s), QPointF(x, box.bottom() - 5 * s))

    def valid(self) -> bool:
        return bool(self.text.strip())


@dataclass
class Loupe:
    """Lupa: amplia o ponto de origem num círculo colocado onde você soltou o mouse."""
    source: QPointF
    center: QPointF
    style: Style
    zoom: float = 2.0

    @property
    def radius(self) -> float:
        return 56 * self.style.scale

    def paint(self, p: QPainter, base: QImage) -> None:
        s, r = self.style.scale, self.radius
        p.save()
        line = QPen(self.style.color, 1.5 * s)
        p.setPen(line)
        p.setBrush(Qt.BrushStyle.NoBrush)
        dx, dy = self.center.x() - self.source.x(), self.center.y() - self.source.y()
        dist = math.hypot(dx, dy)
        if dist > r:
            edge = QPointF(self.center.x() - dx / dist * r, self.center.y() - dy / dist * r)
            p.drawLine(self.source, edge)
        p.drawEllipse(self.source, r / self.zoom, r / self.zoom)
        clip = QPainterPath()
        clip.addEllipse(self.center, r, r)
        p.setClipPath(clip)
        src = QRectF(self.source.x() - r / self.zoom, self.source.y() - r / self.zoom, 2 * r / self.zoom,
                     2 * r / self.zoom)
        p.fillRect(QRectF(self.center.x() - r, self.center.y() - r, 2 * r, 2 * r), QColor("#ffffff"))
        p.drawImage(QRectF(self.center.x() - r, self.center.y() - r, 2 * r, 2 * r), base, src)
        p.setClipping(False)
        p.setPen(QPen(QColor(theme.G950), 5 * s))
        p.drawEllipse(self.center, r, r)
        p.setPen(QPen(self.style.color, 3 * s))
        p.drawEllipse(self.center, r, r)
        p.restore()

    def valid(self) -> bool:
        return True


@dataclass
class Pixelate:
    rect: QRectF
    style: Style

    def block(self, region: QRect) -> int:
        # Blocos grandes o bastante para não dar para "despixelar" uma linha de texto (CPF, CNPJ).
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


@dataclass
class Measure:
    """Régua: distância em pixels do print, em ciano (cor fixa de medida)."""
    start: QPointF
    end: QPointF
    style: Style

    @property
    def length(self) -> int:
        return round(math.hypot(self.end.x() - self.start.x(), self.end.y() - self.start.y()))

    def paint(self, p: QPainter, base: QImage) -> None:
        s = self.style.scale
        cyan = QColor(theme.CYAN)
        dx, dy = self.end.x() - self.start.x(), self.end.y() - self.start.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return
        nx, ny = -dy / length * 7 * s, dx / length * 7 * s
        p.setPen(QPen(cyan, 2 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawLine(self.start, self.end)
        for pt in (self.start, self.end):
            p.drawLine(QPointF(pt.x() - nx, pt.y() - ny), QPointF(pt.x() + nx, pt.y() + ny))
        label = f"{self.length} px"
        p.setFont(theme.font(11 * s, 600, mono=True))
        metrics = QFontMetricsF(p.font())
        box = QRectF(0, 0, metrics.horizontalAdvance(label) + 10 * s, metrics.height() + 4 * s)
        mid = QPointF((self.start.x() + self.end.x()) / 2, (self.start.y() + self.end.y()) / 2)
        box.moveCenter(QPointF(mid.x() + nx * 2.2, mid.y() + ny * 2.2) if abs(dy) > abs(dx)
                       else QPointF(mid.x(), mid.y() - 14 * s))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(cyan)
        p.drawRoundedRect(box, 2 * s, 2 * s)
        p.setPen(QColor(theme.G950))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)

    def valid(self) -> bool:
        return self.length >= MIN_SHAPE


def paint_spotlights(p: QPainter, base: QImage, spots: list[Spotlight]) -> None:
    if not spots:
        return
    s = spots[0].style.scale
    dim = QPainterPath()
    dim.setFillRule(Qt.FillRule.OddEvenFill)
    dim.addRect(QRectF(base.rect()))
    for spot in spots:
        dim.addRoundedRect(spot.rect.normalized(), 2 * s, 2 * s)
    p.fillPath(dim, QColor(18, 17, 16, 140))
    for spot in spots:
        p.setPen(QPen(spot.style.color, 2.5 * s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(spot.rect.normalized(), 2 * s, 2 * s)


def paint_shapes(p: QPainter, base: QImage, shapes: list) -> None:
    """Destaques primeiro (um escurecimento só), depois o resto na ordem em que foi feito."""
    paint_spotlights(p, base, [s for s in shapes if isinstance(s, Spotlight)])
    for shape in shapes:
        if not isinstance(shape, Spotlight):
            shape.paint(p, base)


def render(base: QImage, shapes: list) -> QImage:
    image = base.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    paint_shapes(p, base, shapes)
    p.end()
    return image.convertToFormat(QImage.Format.Format_RGB32)


class Marker(QObject):
    """Estado da marcação de um print: ferramenta, cor, formas e a forma sendo desenhada.

    Recebe posições já em pixels da imagem; quem mostra (overlay ou janela) faz a conversão.
    """

    changed = Signal()
    picked = Signal(str)  # cor copiada pelo conta-gotas

    def __init__(self, base: QImage, scale: float = 1.0):
        super().__init__()
        self.base = base
        self.scale = scale  # px de imagem por px lógico da tela de origem
        self.shapes: list = []
        self.tool = Tool.SPOT
        self.color = QColor(PALETTE[0])
        self.size = 1.0
        self.draft = None
        self.editing: Note | None = None
        self._next_number = 1

    @property
    def next_number(self) -> int:
        return self._next_number

    def set_tool(self, tool: Tool) -> None:
        self.commit_text()
        self.tool = tool
        self.changed.emit()

    def cycle_color(self) -> QColor:
        index = (PALETTE.index(self.color.name()) + 1) % len(PALETTE) if self.color.name() in PALETTE else 0
        self.set_color(QColor(PALETTE[index]))
        return self.color

    def set_color(self, color: QColor) -> None:
        self.color = QColor(color)
        if self.editing:
            self.editing.style.color = QColor(self.color)
        self.changed.emit()

    def set_size(self, size: float) -> None:
        self.size = size
        if self.editing:
            self.editing.style.size = size
        self.changed.emit()

    def add(self, shape) -> None:
        if shape.valid():
            self.shapes.append(shape)
            if isinstance(shape, Step):
                self._next_number = shape.value + 1
            self.changed.emit()

    def undo(self) -> None:
        if self.editing:
            self.editing = None
            self.changed.emit()
            return
        if not self.shapes:
            return
        shape = self.shapes.pop()
        if isinstance(shape, Step):
            self._next_number = shape.value
        self.changed.emit()

    def result(self) -> QImage:
        self.commit_text()
        return render(self.base, self.shapes)

    # --- entrada -----------------------------------------------------------

    def _style(self) -> Style:
        return Style(QColor(self.color), self.scale, self.size)

    def press(self, pos: QPointF) -> None:
        self.commit_text()
        tool = self.tool
        if tool is Tool.SPOT:
            self.draft = Spotlight(QRectF(pos, pos), self._style())
        elif tool is Tool.HIGHLIGHT:
            self.draft = Highlight(QRectF(pos, pos), self._style())
        elif tool is Tool.HIDE:
            self.draft = Pixelate(QRectF(pos, pos), self._style())
        elif tool is Tool.ARROW:
            self.draft = Arrow(pos, pos, self._style())
        elif tool is Tool.MEASURE:
            self.draft = Measure(pos, pos, self._style())
        elif tool is Tool.LOUPE:
            self.draft = Loupe(pos, pos, self._style())
        elif tool is Tool.STEP:
            self.add(Step(pos, self._next_number, self._style()))
        elif tool is Tool.TEXT:
            self.editing = Note(pos, "", self._style(), editing=True)
        elif tool is Tool.PICK:
            point = pos.toPoint()
            if self.base.rect().contains(point):
                color = self.base.pixelColor(point).name().upper()
                QGuiApplication.clipboard().setText(color)
                self.picked.emit(color)
        self.changed.emit()

    def move(self, pos: QPointF) -> None:
        d = self.draft
        if d is None:
            return
        if isinstance(d, (Arrow, Measure)):
            d.end = self._snap(d.start, pos) if isinstance(d, Measure) else pos
        elif isinstance(d, Loupe):
            d.center = pos
        else:
            d.rect.setBottomRight(pos)
        self.changed.emit()

    def release(self, pos: QPointF) -> None:
        draft, self.draft = self.draft, None
        if draft is None:
            return
        if isinstance(draft, Loupe) and math.hypot(draft.center.x() - draft.source.x(),
                                                   draft.center.y() - draft.source.y()) < MIN_SHAPE:
            # Clique simples: a lupa vai para cima e para a direita do ponto.
            offset = draft.radius * 1.6
            draft.center = QPointF(draft.source.x() + offset, draft.source.y() - offset)
        self.add(draft)
        self.changed.emit()

    def type_key(self, event) -> bool:
        """Digitação da nota em edição. True se a tecla foi usada."""
        note = self.editing
        if note is None:
            return False
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.commit_text()
        elif key == Qt.Key.Key_Escape:
            self.editing = None
        elif key == Qt.Key.Key_Backspace:
            note.text = note.text[:-1]
        elif event.text() and event.text().isprintable() and not event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            note.text += event.text()
        else:
            return False
        self.changed.emit()
        return True

    def commit_text(self) -> None:
        note, self.editing = self.editing, None
        if note is not None:
            note.editing = False
            self.add(note)

    @staticmethod
    def _snap(start: QPointF, end: QPointF) -> QPointF:
        angle = abs(math.degrees(math.atan2(end.y() - start.y(), end.x() - start.x()))) % 180
        if min(angle, 180 - angle) < SNAP_DEGREES:
            return QPointF(end.x(), start.y())
        if abs(angle - 90) < SNAP_DEGREES:
            return QPointF(start.x(), end.y())
        return end

    def paint(self, p: QPainter) -> None:
        """Pinta as marcações; o painter já deve estar em coordenadas da imagem."""
        extra = [s for s in (self.draft, self.editing) if s is not None]
        paint_shapes(p, self.base, [*self.shapes, *extra])


class ToolRow(QAbstractButton):
    """Linha da ferramenta no painel: ícone, nome e a tecla de atalho."""

    def __init__(self, icon_name: str, label: str, key: str):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setToolTip(theme.tip(label, key))
        self.setAccessibleName(label)
        self._icon = icon_name
        self._label = label
        self._key = key
        self._hover = False

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        on = self.isChecked()
        if on or self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.G700 if on else theme.G800))
            p.drawRoundedRect(r, 3, 3)
        if on:
            p.fillRect(QRectF(0, 6, 3, r.height() - 12), QColor(theme.S500))
        color = theme.S400 if on else theme.A300
        p.drawPixmap(10, round((r.height() - 18) / 2), icons.pixmap(self._icon, color, 18))
        p.setFont(theme.font(13, 600 if on else 500))
        p.setPen(QColor("#ffffff" if on else theme.A200))
        p.drawText(r.adjusted(38, 0, -36, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)
        key = QRectF(r.right() - 28, r.center().y() - 9, 20, 18)
        p.setPen(QPen(QColor(theme.G600), 1))
        p.setBrush(QColor(theme.G950))
        p.drawRoundedRect(key, 2, 2)
        p.setFont(theme.font(10.5, 500, mono=True))
        p.setPen(QColor(theme.A300))
        p.drawText(key, Qt.AlignmentFlag.AlignCenter, self._key)
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.S500), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)


class Swatch(QAbstractButton):
    """Bolinha de cor; a escolhida ganha um anel."""

    def __init__(self, color: str, name: str):
        super().__init__()
        self.color = QColor(color)
        self.setCheckable(True)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)
        self.setAccessibleName(name)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if self.isChecked():
            p.setPen(QPen(QColor(theme.A50), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 11.5, 11.5)
        p.setPen(QPen(QColor(theme.G600), 1))
        p.setBrush(self.color)
        p.drawEllipse(c, 8, 8)


class MarkBar(QFrame):
    """Painel de marcação ao lado do print: abas Destacar/Analisar, cor, espessura e ações."""

    toolChosen = Signal(object)  # Tool
    colorRequested = Signal()  # tecla C: próxima cor
    colorChosen = Signal(QColor)
    sizeChosen = Signal(float)
    undoRequested = Signal()
    saveRequested = Signal()
    doneRequested = Signal()

    WIDTH = 236

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setStyleSheet(theme.dark_panel_stylesheet())
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFixedWidth(self.WIDTH)
        col = QVBoxLayout(self)
        col.setContentsMargins(10, 10, 10, 10)
        col.setSpacing(8)

        self.tabs = Segmented(TABS, "evidence")
        self.tabs.changed.connect(self._show_tab)
        col.addWidget(self.tabs)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.tools: dict[Tool, ToolRow] = {}
        self._lists: dict[str, QWidget] = {}
        for tab, _ in TABS:
            box = QWidget()
            rows = QVBoxLayout(box)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setSpacing(2)
            self._lists[tab] = box
            col.addWidget(box)
        for entry in TOOLS:
            if entry is None:
                continue
            tool, icon_name, label, key = entry
            row = ToolRow(icon_name, label, key)
            row.clicked.connect(lambda _=False, t=tool: self.toolChosen.emit(t))
            self._group.addButton(row)
            self.tools[tool] = row
            self._lists[TOOL_TAB[tool]].layout().addWidget(row)

        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setProperty("role", "muted")
        self.description.setFont(theme.font(11.5, 400))
        self.description.setMinimumHeight(32)
        col.addWidget(self.description)

        col.addWidget(self._divider())
        col.addWidget(self._section("COR  ·  C troca"))
        swatches = QHBoxLayout()
        swatches.setSpacing(4)
        self._colors = QButtonGroup(self)
        self.swatches: list[Swatch] = []
        for color, name in zip(PALETTE, PALETTE_NAMES):
            sw = Swatch(color, name)
            sw.clicked.connect(lambda _=False, c=color: self.colorChosen.emit(QColor(c)))
            self._colors.addButton(sw)
            self.swatches.append(sw)
            swatches.addWidget(sw)
        swatches.addStretch(1)
        col.addLayout(swatches)

        col.addWidget(self._section("ESPESSURA"))
        self.size = Segmented([(key, label) for key, label, _ in SIZES], "medium")
        self.size.changed.connect(lambda key: self.sizeChosen.emit(next(v for k, _, v in SIZES if k == key)))
        col.addWidget(self.size)

        col.addWidget(self._divider())
        actions = QHBoxLayout()
        actions.setSpacing(4)
        self.undo = icon_button("undo", "Desfazer", "Ctrl Z")
        self.undo.clicked.connect(self.undoRequested.emit)
        self.save = icon_button("save", "Salvar", "Ctrl S")
        self.save.clicked.connect(self.saveRequested.emit)
        self.done = button("Copiar", "primary", "check")
        self.done.setToolTip(theme.tip("Copiar o print marcado", "Enter"))
        self.done.clicked.connect(self.doneRequested.emit)
        actions.addWidget(self.undo)
        actions.addWidget(self.save)
        actions.addStretch(1)
        actions.addWidget(self.done)
        col.addLayout(actions)

        self.set_tool(Tool.SPOT)
        self.set_color(QColor(PALETTE[0]))
        self.adjustSize()

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame(objectName="divider")
        line.setFixedHeight(1)
        return line

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "section")
        return label

    def _show_tab(self, tab: str) -> None:
        for key, box in self._lists.items():
            box.setVisible(key == tab)

    def set_tool(self, tool: Tool) -> None:
        tab = TOOL_TAB[tool]
        if self.tabs.value != tab:
            self.tabs.buttons[tab].setChecked(True)
        self._show_tab(tab)
        self.tools[tool].setChecked(True)
        self.description.setText(DESCRIPTIONS[tool])

    def set_color(self, color: QColor) -> None:
        for sw in self.swatches:
            sw.setChecked(sw.color.name() == color.name())


class Canvas(QWidget):
    """Mostra o print na janela de marcar e repassa o mouse ao Marker em pixels da imagem."""

    def __init__(self, marker: Marker, view_scale: float):
        super().__init__()
        self.marker = marker
        self._view = view_scale  # px de widget por px de imagem
        marker.changed.connect(self.update)
        self.setFixedSize(QSize(round(marker.base.width() * view_scale), round(marker.base.height() * view_scale)))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _to_image(self, pos: QPointF) -> QPointF:
        return QPointF(pos.x() / self._view, pos.y() / self._view)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.marker.press(self._to_image(event.position()))

    def mouseMoveEvent(self, event) -> None:
        self.marker.move(self._to_image(event.position()))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.marker.release(self._to_image(event.position()))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(self._view, self._view)
        p.drawImage(0, 0, self.marker.base)
        self.marker.paint(p)


def handle_mark_key(marker: Marker, bar: MarkBar, event) -> bool:
    """Teclas da marcação, iguais na captura e na janela. True se a tecla foi usada."""
    if marker.type_key(event):
        return True
    plain = event.modifiers() in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier)
    if plain and event.key() in KEYS:
        marker.set_tool(KEYS[event.key()])
        bar.set_tool(KEYS[event.key()])
        return True
    if plain and event.key() == Qt.Key.Key_C:
        bar.set_color(marker.cycle_color())
        return True
    if event.matches(QKeySequence.StandardKey.Undo):
        marker.undo()
        return True
    return False


class EditorWindow(QWidget):
    """Janela leve de marcar (usada pela galeria e pelo aviso pós-captura)."""

    done = Signal(object, QImage)  # Action.COPY ou Action.SAVE, imagem final

    def __init__(self, image: QImage, image_scale: float = 1.0):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("editor")
        self.setWindowTitle("Klick: marcar")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(f"QWidget#editor {{ background: {theme.G950}; }} QScrollArea {{ border: none; background: {theme.G950}; }}")

        screen = QGuiApplication.primaryScreen().availableGeometry()
        view = min(1 / image_scale, screen.width() * 0.8 / image.width(), screen.height() * 0.8 / image.height())
        self.marker = Marker(image, image_scale)
        self.canvas = Canvas(self.marker, view)
        self.bar = MarkBar()
        self.bar.toolChosen.connect(self.set_tool)
        self.bar.colorRequested.connect(lambda: self.bar.set_color(self.marker.cycle_color()))
        self.bar.colorChosen.connect(self.set_color)
        self.bar.sizeChosen.connect(self.marker.set_size)
        self.bar.undoRequested.connect(self.marker.undo)
        self.bar.saveRequested.connect(lambda: self._finish(Action.SAVE))
        self.bar.doneRequested.connect(lambda: self._finish(Action.COPY))

        QShortcut(QKeySequence.StandardKey.Copy, self, activated=lambda: self._finish(Action.COPY))
        QShortcut(QKeySequence.StandardKey.Save, self, activated=lambda: self._finish(Action.SAVE))

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(12)
        row.addWidget(scroll, 1)
        row.addWidget(self.bar, 0, Qt.AlignmentFlag.AlignTop)
        self.resize(self.canvas.width() + self.bar.sizeHint().width() + 60,
                    max(self.canvas.height(), self.bar.sizeHint().height()) + 40)

    # compatível com quem usava editor.canvas.shapes
    @property
    def shapes(self) -> list:
        return self.marker.shapes

    def set_tool(self, tool: Tool) -> None:
        self.marker.set_tool(tool)
        self.bar.set_tool(tool)

    def set_color(self, color) -> None:
        self.marker.set_color(QColor(color))
        self.bar.set_color(self.marker.color)

    def keyPressEvent(self, event) -> None:
        if handle_mark_key(self.marker, self.bar, event):
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish(Action.COPY)
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def _finish(self, action: Action) -> None:
        self.done.emit(action, self.marker.result())
        self.close()
