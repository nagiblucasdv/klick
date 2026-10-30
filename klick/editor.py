"""Editar imagem: formas (caixa, elipse, seta, linha), destaque (destaque, marca-texto, caneta,
número, texto) e proteção/análise (pixelar, desfocar, lupa, medir, conta-gotas).

As marcações ficam numa lista de formas sobre a imagem original, em pixels da imagem;
nada é "queimado" até o render final, então desfazer é só um pop. O mesmo `Marker`
serve à edição dentro da própria captura (overlay) e à janela de editar da galeria.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFontMetricsF, QGuiApplication, QImage, QKeySequence, QPainter, QPainterPath,
                           QPen, QPolygonF, QShortcut)
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

from klick import theme
from klick.actions import Action
from klick.icon import app_icon
from klick.widgets import Segmented, button, icon_button

# Cores de anotação: fortes o bastante para ler sobre qualquer print.
PALETTE = ["#e5484d", "#f08c00", "#ffd43b", "#2f9e44", "#1c7ed6", "#1e1b18", "#ffffff"]
PALETTE_NAMES = ["Vermelho", "Laranja", "Amarelo", "Verde", "Azul", "Preto", "Branco"]
SIZES = [("thin", "Fina", 0.66), ("medium", "Média", 1.0), ("thick", "Grossa", 1.6)]
MIN_SHAPE = 4  # px de imagem; menor que isso é clique perdido
SNAP_DEGREES = 4  # a régua e a linha grudam na horizontal/vertical perto disso


class Tool(str, Enum):
    BOX = "box"
    ELLIPSE = "ellipse"
    ARROW = "arrow"
    LINE = "line"
    SPOT = "spot"
    HIGHLIGHT = "highlight"
    PEN = "pen"
    STEP = "step"
    TEXT = "text"
    HIDE = "hide"
    BLUR = "blur"
    LOUPE = "loupe"
    MEASURE = "measure"
    PICK = "pick"


# (ferramenta, ícone, nome, tecla); None separa grupos: formas | destacar | proteger e analisar
TOOLS = [
    (Tool.BOX, "box", "Caixa", "B"),
    (Tool.ELLIPSE, "ellipse", "Elipse", "O"),
    (Tool.ARROW, "arrow", "Seta", "A"),
    (Tool.LINE, "line", "Linha", "L"),
    None,
    (Tool.SPOT, "spot", "Destaque", "D"),
    (Tool.HIGHLIGHT, "mark", "Marca-texto", "M"),
    (Tool.PEN, "pen", "Caneta", "F"),
    (Tool.STEP, "step", "Número", "N"),
    (Tool.TEXT, "text", "Texto", "T"),
    None,
    (Tool.HIDE, "hide", "Pixelar", "P"),
    (Tool.BLUR, "blur", "Desfocar", "U"),
    (Tool.LOUPE, "loupe", "Lupa", "Z"),
    (Tool.MEASURE, "ruler", "Medir", "R"),
    (Tool.PICK, "drop", "Conta-gotas", "I"),
]
KEYS = {Qt.Key(ord(key)): tool for entry in TOOLS if entry for tool, _, _, key in [entry]}
# O que cada ferramenta faz, mostrado embaixo da barra.
DESCRIPTIONS = {
    Tool.BOX: "Caixa: arraste para contornar uma área.",
    Tool.ELLIPSE: "Elipse: arraste para circular um ponto.",
    Tool.ARROW: "Seta: arraste do ponto de partida até o alvo.",
    Tool.LINE: "Linha: arraste. Gruda na horizontal e na vertical.",
    Tool.SPOT: "Destaque: arraste uma área e o resto do print escurece.",
    Tool.HIGHLIGHT: "Marca-texto: pinta por cima, como caneta marca-texto.",
    Tool.PEN: "Caneta: desenhe à mão livre.",
    Tool.STEP: "Número: cada clique põe 1, 2, 3… Bom para passo a passo.",
    Tool.TEXT: "Texto: clique e digite. Enter termina.",
    Tool.HIDE: "Pixelar: esconde CPF, senha e outros dados.",
    Tool.BLUR: "Desfocar: borra a área, mais suave que pixelar.",
    Tool.LOUPE: "Lupa: arraste do detalhe até onde a lupa fica.",
    Tool.MEASURE: "Medir: distância em pixels.",
    Tool.PICK: "Conta-gotas: clique para copiar a cor (#hex).",
}


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
    return QColor(theme.PAPER) if color.lightness() > 150 else QColor("#ffffff")


def _shadow(style: Style) -> QPen:
    """Contorno escuro fino por baixo do traço: lê em fundo claro e escuro."""
    return QPen(QColor(18, 17, 16, 90), style.width + 2 * style.scale, Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _stroke(style: Style) -> QPen:
    return QPen(style.color, style.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


@dataclass
class Box:
    """Caixa: contorno de uma área."""
    rect: QRectF
    style: Style
    round_: bool = False  # elipse

    def paint(self, p: QPainter, base: QImage) -> None:
        r = self.rect.normalized()
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        for pen in (_shadow(self.style), _stroke(self.style)):
            p.setPen(pen)
            if self.round_:
                p.drawEllipse(r)
            else:
                p.drawRoundedRect(r, 3 * self.style.scale, 3 * self.style.scale)
        p.restore()

    def valid(self) -> bool:
        r = self.rect.normalized()
        return r.width() >= MIN_SHAPE and r.height() >= MIN_SHAPE


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
    head: bool = True  # sem ponta é uma linha

    def paint(self, p: QPainter, base: QImage) -> None:
        w = self.style.width
        length = math.hypot(self.end.x() - self.start.x(), self.end.y() - self.start.y())
        if length < 1:
            return
        if not self.head:
            for pen in (_shadow(self.style), _stroke(self.style)):
                p.setPen(pen)
                p.drawLine(self.start, self.end)
            return
        head = min(w * 5, length * 0.6)
        angle = math.atan2(self.end.y() - self.start.y(), self.end.x() - self.start.x())
        neck = QPointF(self.end.x() - head * 0.8 * math.cos(angle), self.end.y() - head * 0.8 * math.sin(angle))
        p.setPen(_shadow(self.style))
        p.drawLine(self.start, neck)
        p.setPen(_stroke(self.style))
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
class Stroke:
    """Caneta: traço à mão livre."""
    points: list[QPointF]
    style: Style

    def paint(self, p: QPainter, base: QImage) -> None:
        if len(self.points) < 2:
            return
        path = QPainterPath(self.points[0])
        for pt in self.points[1:]:
            path.lineTo(pt)
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        for pen in (_shadow(self.style), _stroke(self.style)):
            p.setPen(pen)
            p.drawPath(path)
        p.restore()

    def valid(self) -> bool:
        if len(self.points) < 2:
            return False
        xs = [pt.x() for pt in self.points]
        ys = [pt.y() for pt in self.points]
        return max(max(xs) - min(xs), max(ys) - min(ys)) >= MIN_SHAPE


@dataclass
class Step:
    """Número (1, 2, 3) para passo a passo."""
    center: QPointF
    value: int
    style: Style

    def paint(self, p: QPainter, base: QImage) -> None:
        s = self.style.unit
        r = 13 * s
        p.setPen(QPen(QColor("#ffffff"), 2 * s))
        p.setBrush(self.style.color)
        p.drawEllipse(self.center, r, r)
        p.setFont(theme.font(15 * s, 800))
        p.setPen(_ink(self.style.color))
        p.drawText(QRectF(self.center.x() - r, self.center.y() - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter,
                   str(self.value))

    def valid(self) -> bool:
        return True


@dataclass
class Note:
    """Nota de texto: etiqueta clara com a barra da cor. Digitada direto, sem diálogo."""
    pos: QPointF
    text: str
    style: Style
    editing: bool = False

    def box(self) -> QRectF:
        s = self.style.unit
        metrics = QFontMetricsF(theme.font(14 * s, 600))
        width = max(metrics.horizontalAdvance(self.text or "Digite"), 40 * s)
        return QRectF(self.pos.x(), self.pos.y(), width + 22 * s, metrics.height() + 12 * s)

    def paint(self, p: QPainter, base: QImage) -> None:
        s = self.style.unit
        box = self.box()
        p.setPen(QPen(QColor(theme.G600), 1 * s))
        p.setBrush(QColor(theme.G850))
        p.drawRoundedRect(box, 6 * s, 6 * s)
        p.fillRect(QRectF(box.left() + 1 * s, box.top() + 4 * s, 4 * s, box.height() - 8 * s), self.style.color)
        p.setFont(theme.font(14 * s, 600))
        text_box = box.adjusted(12 * s, 0, -8 * s, 0)
        if self.text:
            p.setPen(QColor(theme.PAPER))
            p.drawText(text_box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text)
        elif self.editing:
            p.setPen(QColor(theme.G500))
            p.drawText(text_box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Digite")
        if self.editing:
            x = text_box.left() + QFontMetricsF(theme.font(14 * s, 600)).horizontalAdvance(self.text) + 1 * s
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
        p.setPen(QPen(QColor("#ffffff"), 5 * s))
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
    soft: bool = False  # desfocar em vez de pixelar

    def block(self, region: QRect) -> int:
        # Blocos grandes o bastante para não dar para "despixelar" uma linha de texto (CPF, CNPJ).
        return max(round(10 * self.style.scale), min(region.width(), region.height()) // 3, 2)

    def paint(self, p: QPainter, base: QImage) -> None:
        region = self.rect.normalized().toAlignedRect().intersected(base.rect())
        if region.isEmpty():
            return
        if self.soft:
            p.drawImage(QRectF(region), blur(base.copy(region), max(4, round(6 * self.style.scale))))
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


def blur(image: QImage, factor: int) -> QImage:
    """Desfoque barato: reduz e amplia duas vezes com suavização (sem bordas duras de bloco)."""
    w, h = image.width(), image.height()
    out = image
    for _ in range(2):
        small = out.scaled(max(1, w // factor), max(1, h // factor), Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        out = small.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return out


@dataclass
class Measure:
    """Régua: distância em pixels do print, na cor de medida."""
    start: QPointF
    end: QPointF
    style: Style

    @property
    def length(self) -> int:
        return round(math.hypot(self.end.x() - self.start.x(), self.end.y() - self.start.y()))

    def paint(self, p: QPainter, base: QImage) -> None:
        s = self.style.scale
        ink = QColor(theme.S500)
        dx, dy = self.end.x() - self.start.x(), self.end.y() - self.start.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return
        nx, ny = -dy / length * 7 * s, dx / length * 7 * s
        p.setPen(QPen(ink, 2 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawLine(self.start, self.end)
        for pt in (self.start, self.end):
            p.drawLine(QPointF(pt.x() - nx, pt.y() - ny), QPointF(pt.x() + nx, pt.y() + ny))
        label = f"{self.length} px"
        p.setFont(theme.font(11 * s, 600, mono=True))
        metrics = QFontMetricsF(p.font())
        box = QRectF(0, 0, metrics.horizontalAdvance(label) + 12 * s, metrics.height() + 4 * s)
        mid = QPointF((self.start.x() + self.end.x()) / 2, (self.start.y() + self.end.y()) / 2)
        box.moveCenter(QPointF(mid.x() + nx * 2.2, mid.y() + ny * 2.2) if abs(dy) > abs(dx)
                       else QPointF(mid.x(), mid.y() - 14 * s))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawRoundedRect(box, box.height() / 2, box.height() / 2)
        p.setPen(QColor(theme.INK))
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
    """Estado da edição de um print: ferramenta, cor, formas e a forma sendo desenhada.

    Recebe posições já em pixels da imagem; quem mostra (overlay ou janela) faz a conversão.
    """

    changed = Signal()
    picked = Signal(str)  # cor copiada pelo conta-gotas

    def __init__(self, base: QImage, scale: float = 1.0):
        super().__init__()
        self.base = base
        self.scale = scale  # px de imagem por px lógico da tela de origem
        self.shapes: list = []
        self.tool = Tool.BOX
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
        tool, style = self.tool, self._style()
        rect = QRectF(pos, pos)
        drafts = {
            Tool.BOX: lambda: Box(rect, style),
            Tool.ELLIPSE: lambda: Box(rect, style, round_=True),
            Tool.SPOT: lambda: Spotlight(rect, style),
            Tool.HIGHLIGHT: lambda: Highlight(rect, style),
            Tool.HIDE: lambda: Pixelate(rect, style),
            Tool.BLUR: lambda: Pixelate(rect, style, soft=True),
            Tool.ARROW: lambda: Arrow(pos, pos, style),
            Tool.LINE: lambda: Arrow(pos, pos, style, head=False),
            Tool.PEN: lambda: Stroke([pos], style),
            Tool.MEASURE: lambda: Measure(pos, pos, style),
            Tool.LOUPE: lambda: Loupe(pos, pos, style),
        }
        if tool in drafts:
            self.draft = drafts[tool]()
        elif tool is Tool.STEP:
            self.add(Step(pos, self._next_number, style))
        elif tool is Tool.TEXT:
            self.editing = Note(pos, "", style, editing=True)
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
        if isinstance(d, Stroke):
            d.points.append(pos)
        elif isinstance(d, (Arrow, Measure)):
            snap = isinstance(d, Measure) or (isinstance(d, Arrow) and not d.head)
            d.end = self._snap(d.start, pos) if snap else pos
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


class Swatch(QAbstractButton):
    """Bolinha de cor; a escolhida ganha um anel."""

    def __init__(self, color: str, name: str):
        super().__init__()
        self.color = QColor(color)
        self.setCheckable(True)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)
        self.setAccessibleName(name)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if self.isChecked():
            p.setPen(QPen(QColor(theme.PAPER), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 10.5, 10.5)
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(self.color)
        p.drawEllipse(c, 7.5, 7.5)


class EditBar(QFrame):
    """Barra de editar: as ferramentas numa linha só, embaixo cor, espessura e as ações."""

    toolChosen = Signal(object)  # Tool
    colorChosen = Signal(QColor)
    sizeChosen = Signal(float)
    undoRequested = Signal()
    saveRequested = Signal()
    doneRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setStyleSheet(theme.dark_panel_stylesheet())
        self.setCursor(Qt.CursorShape.ArrowCursor)
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.tools: dict[Tool, QToolButton] = {}
        for entry in TOOLS:
            if entry is None:
                row.addSpacing(4)
                row.addWidget(self._divider())
                row.addSpacing(4)
                continue
            tool, icon_name, label, key = entry
            b = icon_button(icon_name, label, key, size=34)
            b.setCheckable(True)
            b.setAutoRaise(False)
            b.clicked.connect(lambda _=False, t=tool: self.toolChosen.emit(t))
            self._group.addButton(b)
            self.tools[tool] = b
            row.addWidget(b)
        col.addLayout(row)

        row = QHBoxLayout()
        row.setSpacing(3)
        self._colors = QButtonGroup(self)
        self.swatches: list[Swatch] = []
        for color, name in zip(PALETTE, PALETTE_NAMES):
            sw = Swatch(color, f"{name} (C troca)")
            sw.clicked.connect(lambda _=False, c=color: self.colorChosen.emit(QColor(c)))
            self._colors.addButton(sw)
            self.swatches.append(sw)
            row.addWidget(sw)
        row.addSpacing(8)
        self.size = Segmented([(key, label) for key, label, _ in SIZES], "medium")
        self.size.changed.connect(lambda key: self.sizeChosen.emit(next(v for k, _, v in SIZES if k == key)))
        row.addWidget(self.size)
        row.addStretch(1)
        self.undo = icon_button("undo", "Desfazer", "Ctrl Z")
        self.undo.clicked.connect(self.undoRequested.emit)
        self.save = icon_button("save", "Salvar", "Ctrl S")
        self.save.clicked.connect(self.saveRequested.emit)
        self.done = button("Copiar", "primary", "check")
        self.done.setToolTip(theme.tip("Copiar a imagem editada", "Enter"))
        self.done.clicked.connect(self.doneRequested.emit)
        row.addWidget(self.undo)
        row.addWidget(self.save)
        row.addWidget(self.done)
        col.addLayout(row)

        self.description = QLabel()
        self.description.setProperty("role", "muted")
        self.description.setFont(theme.font(12, 500))
        self.description.setContentsMargins(4, 0, 0, 0)
        col.addWidget(self.description)

        self.set_tool(Tool.BOX)
        self.set_color(QColor(PALETTE[0]))
        self.adjustSize()

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame(objectName="divider")
        line.setFixedSize(1, 22)
        return line

    def set_tool(self, tool: Tool) -> None:
        self.tools[tool].setChecked(True)
        self.description.setText(DESCRIPTIONS[tool])

    def set_color(self, color: QColor) -> None:
        for sw in self.swatches:
            sw.setChecked(sw.color.name() == color.name())


class Canvas(QWidget):
    """Mostra o print na janela de editar e repassa o mouse ao Marker em pixels da imagem."""

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


def handle_mark_key(marker: Marker, bar: EditBar, event) -> bool:
    """Teclas da edição, iguais na captura e na janela. True se a tecla foi usada."""
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
    """Janela de editar imagem (usada pela galeria e pelo aviso pós-captura): a barra em cima e o print
    embaixo, do tamanho do print, sem sobra."""

    done = Signal(object, QImage)  # Action.COPY ou Action.SAVE, imagem final

    def __init__(self, image: QImage, image_scale: float = 1.0):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("editor")
        self.setWindowTitle("Klick: editar imagem")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(f"QWidget#editor {{ background: {theme.G950}; }}"
                           f" QScrollArea {{ border: none; background: {theme.G950}; }}"
                           f" QFrame#panel {{ background: {theme.G900}; border: 1px solid {theme.G700};"
                           f" border-radius: {theme.WINDOW_RADIUS}px; }}")

        screen = QGuiApplication.primaryScreen().availableGeometry()
        view = min(1 / image_scale, screen.width() * 0.85 / image.width(), screen.height() * 0.75 / image.height())
        self.marker = Marker(image, image_scale)
        self.canvas = Canvas(self.marker, view)
        self.bar = EditBar()
        self.bar.toolChosen.connect(self.set_tool)
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
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 12, 12, 12)
        col.setSpacing(10)
        col.addWidget(self.bar, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(scroll, 1)
        bar = self.bar.sizeHint()
        self.resize(max(self.canvas.width(), bar.width()) + 28, self.canvas.height() + bar.height() + 40)

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
