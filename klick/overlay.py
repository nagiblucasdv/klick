"""Overlay fullscreen onde o usuário arrasta o retângulo de seleção.

Um overlay por monitor, cada um mostrando a imagem congelada daquele monitor.
A seleção fica restrita a um monitor por vez.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QCursor, QGuiApplication, QImage, QKeySequence, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from klick import icons, theme
from klick.actions import Action
from klick.capture import ScreenShot, Selection, to_physical
from klick.editor import MarkBar, Marker, Tool, handle_mark_key

MIN_SIZE = 3  # seleções menores que isso são tratadas como clique
CORNER = 14  # braço dos cantos do visor
LOUPE_PX = 15  # pixels de tela mostrados na lupa (ímpar: o do meio é o do cursor)
LOUPE_ZOOM = 8

CTRL_KEYS = {
    Qt.Key.Key_T: Action.READ,
    Qt.Key.Key_E: Action.EDIT,
    Qt.Key.Key_R: Action.RECORD,
    Qt.Key.Key_G: Action.GIF,
}
HINTS = {
    Action.OCR: "Selecione o texto",
    Action.RECORD: "Selecione a área para gravar",
    Action.GIF: "Selecione a área para gravar em GIF",
}

# (ação, ícone, rótulo, tooltip, atalho); None separa grupos
TOOLBAR = [
    (Action.COPY, "copy", "Copiar", "Copiar", "Enter"),
    (Action.READ, "read", "Ler", "Ler o texto", "Ctrl T"),
    (Action.EDIT, "mark", "Marcar", "Marcar e destacar", "Ctrl E"),
    (Action.SAVE, "save", "Salvar", "Salvar em arquivo", "Ctrl S"),
    None,
    (Action.RECORD, "rec", "Gravar", "Gravar vídeo", "Ctrl R"),
    (Action.GIF, "gif", "GIF", "Gravar GIF", "Ctrl G"),
    None,
    (None, "close", "Fechar", "Cancelar", "Esc"),
]

TOOLBAR_STYLE = theme.dark_panel_stylesheet() + f"""
QToolButton {{ padding: 6px 6px 4px; min-width: 40px; }}
QToolButton[primary="true"] {{ background: {theme.S500}; color: {theme.G950}; border-bottom: 2px solid #c94c00; }}
QToolButton[primary="true"]:hover {{ background: {theme.S400}; }}
"""


class Toolbar(QFrame):
    triggered = Signal(object)  # Action
    closeRequested = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setStyleSheet(TOOLBAR_STYLE)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        label_font = theme.font(11, 600, 88)
        self.buttons: dict[Action | None, QToolButton] = {}
        for entry in TOOLBAR:
            if entry is None:
                divider = QFrame(objectName="divider")
                divider.setFixedWidth(1)
                layout.addWidget(divider)
                continue
            action, icon_name, label, tip, key = entry
            primary = action is Action.COPY
            color = theme.REC if action is Action.RECORD else (theme.G950 if primary else theme.A300)
            hover = color if action is Action.RECORD or primary else theme.S400
            button = QToolButton()
            button.setText(label)
            button.setIcon(icons.icon(icon_name, color, hover=hover))
            button.setIconSize(QSize(18, 18))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setFont(label_font)
            button.setToolTip(theme.tip(tip, key))
            button.setProperty("primary", primary)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if action is None:
                button.clicked.connect(self.closeRequested.emit)
            else:
                button.clicked.connect(lambda _=False, a=action: self.triggered.emit(a))
            self.buttons[action] = button
            layout.addWidget(button)
        self.adjustSize()
        self.hide()


class SelectionOverlay(QWidget):
    selected = Signal(object, object)  # Action, Selection
    cancelled = Signal()
    selectionStarted = Signal()

    def __init__(self, shot: ScreenShot, direct_action: Action | None = None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self._image = shot.image
        self._screen_origin = shot.origin
        self._direct_action = direct_action
        self._selection = QRectF()
        self._origin = QPointF()
        self._drag: str | None = None  # "create" | "move"
        self._cursor: QPointF | None = None
        self._picked: str | None = None  # cor copiada com C, mostrada na lupa
        self._marker: Marker | None = None  # marcação dentro da própria captura
        self._markbar: MarkBar | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setScreen(shot.screen)
        self.setGeometry(shot.screen.geometry())

        self._toolbar = Toolbar(self)
        self._toolbar.triggered.connect(self._finish)
        self._toolbar.closeRequested.connect(self.cancelled.emit)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # --- API ---------------------------------------------------------------

    @property
    def selection(self) -> QRectF:
        return QRectF(self._selection)

    def clear_selection(self) -> None:
        self.exit_mark()
        self._selection = QRectF()
        self._toolbar.hide()
        self.update()

    @property
    def marking(self) -> bool:
        return self._marker is not None

    @property
    def marker(self) -> Marker | None:
        return self._marker

    def enter_mark(self) -> None:
        """Marca o print aqui mesmo: a barra vira a régua de ferramentas ao lado da seleção."""
        if not self._has_selection() or self._marker is not None:
            return
        self._toolbar.hide()
        self._marker = Marker(self.cropped(), self._image.width() / max(1, self.width()))
        self._marker.changed.connect(self.update)
        self._marker.picked.connect(self._on_picked)
        if self._markbar is None:
            bar = MarkBar(self)
            bar.toolChosen.connect(self._set_tool)
            bar.colorRequested.connect(lambda: bar.set_color(self._marker.cycle_color()))
            bar.undoRequested.connect(lambda: self._marker.undo())
            bar.saveRequested.connect(lambda: self._finish(Action.SAVE))
            bar.doneRequested.connect(lambda: self._finish(Action.COPY))
            self._markbar = bar
        self._markbar.set_tool(Tool.SPOT)
        self._markbar.set_color(self._marker.color)
        self._place_markbar()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def exit_mark(self) -> None:
        if self._marker is None:
            return
        self._marker = None
        if self._markbar is not None:
            self._markbar.hide()
        if self._has_selection():
            self._place_toolbar()
        self.update()

    def cropped(self) -> QImage:
        rect = to_physical(self._selection, self.size(), self._image.size())
        return self._image.copy(rect)

    def current(self) -> Selection:
        rect = to_physical(self._selection, self.size(), self._image.size())
        marked = self._marker is not None and bool(self._marker.shapes or self._marker.editing)
        return Selection(
            image=self._marker.result() if marked else self._image.copy(rect),
            rect=rect.translated(self._screen_origin),
            logical=self._selection.toAlignedRect().translated(self.geometry().topLeft()),
            screen=self.screen(),
            marked=marked,
        )

    def pixel_at(self, pos: QPointF) -> QPoint:
        """Pixel físico da imagem congelada sob um ponto lógico do overlay."""
        sx = self._image.width() / max(1, self.width())
        sy = self._image.height() / max(1, self.height())
        return QPoint(min(int(pos.x() * sx), self._image.width() - 1), min(int(pos.y() * sy), self._image.height() - 1))

    # --- eventos -----------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def enterEvent(self, event) -> None:
        # Garante que Esc/atalhos funcionem no monitor onde o mouse está.
        self.activateWindow()
        self.setFocus()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._cursor = None
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if self._marker is not None:
            if handle_mark_key(self._marker, self._markbar, event):
                self.update()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.exit_mark()
                return
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or event.matches(QKeySequence.StandardKey.Copy):
            self._finish(Action.COPY)
        elif event.matches(QKeySequence.StandardKey.Save):
            self._finish(Action.SAVE)
        elif event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() in CTRL_KEYS:
            self._finish(CTRL_KEYS[event.key()])
        elif event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.NoModifier and self._cursor:
            self._pick_color()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.position()
        if self._marker is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._marker.press(self._to_crop(pos))
            return
        if event.button() == Qt.MouseButton.RightButton:
            if self._has_selection():
                self.clear_selection()
            else:
                self.cancelled.emit()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._toolbar.hide()
        if self._has_selection() and self._selection.contains(pos):
            self._drag = "move"
            self._origin = pos - self._selection.topLeft()
        else:
            self._drag = "create"
            self._origin = pos
            self._selection = QRectF(pos, pos)
            self.selectionStarted.emit()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        pos = self._clamp(event.position())
        self._cursor = pos
        self._picked = None
        if self._marker is not None:
            self._marker.move(self._to_crop(pos))
            self.update()
            return
        if self._drag == "create":
            self._selection = QRectF(self._origin, pos).normalized()
        elif self._drag == "move":
            rect = QRectF(self._selection)
            rect.moveTopLeft(pos - self._origin)
            self._selection = self._keep_inside(rect)
        else:
            inside = self._has_selection() and self._selection.contains(event.position())
            self.setCursor(Qt.CursorShape.SizeAllCursor if inside else Qt.CursorShape.CrossCursor)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._marker is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._marker.release(self._to_crop(event.position()))
            return
        if event.button() != Qt.MouseButton.LeftButton or self._drag is None:
            return
        self._drag = None
        if not self._has_selection():
            self.clear_selection()
            return
        if self._direct_action is not None:
            self._finish(self._direct_action)
            return
        self._place_toolbar()
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._marker is not None:
            return
        if self._has_selection() and self._selection.contains(event.position()):
            self._finish(Action.COPY)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.drawImage(self.rect(), self._image)

        dim = QPainterPath()
        dim.setFillRule(Qt.FillRule.OddEvenFill)
        dim.addRect(QRectF(self.rect()))
        if self._has_selection():
            dim.addRect(self._selection)
        p.fillPath(dim, theme.DIM)

        if self._marker is not None:
            scale = self._marker.scale
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setClipRect(self._selection)
            p.translate(self._selection.topLeft())
            p.scale(1 / scale, 1 / scale)
            self._marker.paint(p)
            p.restore()
        if self._has_selection():
            self._draw_selection(p)
        elif self._drag is None:
            hint = HINTS.get(self._direct_action, "Arraste para selecionar")
            self._draw_hint(p, hint)
        picking = self._marker is not None and self._marker.tool is Tool.PICK
        if self._cursor is not None and self._drag != "move" and not self._toolbar.isVisible() \
                and (self._marker is None or picking):
            self._draw_loupe(p, self._cursor)

    # --- internos ----------------------------------------------------------

    def _finish(self, action: Action) -> None:
        if not self._has_selection():
            return
        if action is Action.EDIT and self._direct_action is None:
            self.enter_mark()
            return
        self.selected.emit(action, self.current())

    def _to_crop(self, pos: QPointF) -> QPointF:
        """Ponto lógico do overlay -> pixel do recorte que está sendo marcado."""
        scale = self._marker.scale
        return QPointF((pos.x() - self._selection.left()) * scale, (pos.y() - self._selection.top()) * scale)

    def _set_tool(self, tool: Tool) -> None:
        self._marker.set_tool(tool)
        self.update()

    def _on_picked(self, color: str) -> None:
        self._picked = color
        self.update()

    def _place_markbar(self) -> None:
        bar = self._markbar
        bar.adjustSize()
        gap = 10
        sel = self._selection
        x = sel.right() + gap
        if x + bar.width() > self.width():
            x = sel.left() - gap - bar.width()
        if x < 0:
            x = sel.right() - bar.width() - gap  # sem espaço dos lados: fica dentro, à direita
        y = min(max(sel.top(), 4), self.height() - bar.height() - 4)
        bar.move(round(x), round(y))
        bar.show()
        bar.raise_()

    def _has_selection(self) -> bool:
        return self._selection.width() >= MIN_SIZE and self._selection.height() >= MIN_SIZE

    def _clamp(self, pos: QPointF) -> QPointF:
        return QPointF(min(max(pos.x(), 0), self.width() - 1), min(max(pos.y(), 0), self.height() - 1))

    def _keep_inside(self, rect: QRectF) -> QRectF:
        x = min(max(rect.x(), 0), self.width() - rect.width())
        y = min(max(rect.y(), 0), self.height() - rect.height())
        rect.moveTo(x, y)
        return rect

    def _pick_color(self) -> None:
        color = self._image.pixelColor(self.pixel_at(self._cursor)).name().upper()
        QGuiApplication.clipboard().setText(color)
        self._picked = color
        self.update()

    def _place_toolbar(self) -> None:
        tb = self._toolbar
        tb.adjustSize()
        gap = 8
        sel = self._selection
        x = sel.left()
        y = sel.bottom() + gap
        if y + tb.height() > self.height():
            y = sel.top() - tb.height() - gap - 26  # acima, deixando lugar para a medida
        if y < 0:
            y = sel.bottom() - tb.height() - gap
        x = min(max(x, 4), self.width() - tb.width() - 4)
        tb.move(round(x), round(y))
        tb.show()
        tb.raise_()

    def _draw_selection(self, p: QPainter) -> None:
        sel = self._selection
        pen = QPen(QColor(247, 246, 243, 230), 1)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawRect(sel)

        if self._drag == "create":
            # Linhas dos terços enquanto arrasta, como no visor de uma câmera.
            guide = QPen(QColor(255, 255, 255, 70), 1)
            guide.setCosmetic(True)
            p.setPen(guide)
            for i in (1, 2):
                x = sel.left() + sel.width() * i / 3
                y = sel.top() + sel.height() * i / 3
                p.drawLine(QPointF(x, sel.top()), QPointF(x, sel.bottom()))
                p.drawLine(QPointF(sel.left(), y), QPointF(sel.right(), y))

        corner = QPen(QColor(theme.S500), 3)
        corner.setCapStyle(Qt.PenCapStyle.SquareCap)
        corner.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(corner)
        arm = min(CORNER, sel.width() / 2, sel.height() / 2)
        for x, dx in ((sel.left() - 1, arm), (sel.right() + 1, -arm)):
            for y, dy in ((sel.top() - 1, arm), (sel.bottom() + 1, -arm)):
                p.drawPolyline([QPointF(x + dx, y), QPointF(x, y), QPointF(x, y + dy)])

        phys = to_physical(sel, self.size(), self._image.size())
        self._badge(p, f"{phys.width()} × {phys.height()}", sel.topLeft())

    def _badge(self, p: QPainter, text: str, anchor: QPointF) -> None:
        p.setFont(theme.font(12, 600, mono=True))
        metrics = p.fontMetrics()
        box = QRectF(0, 0, metrics.horizontalAdvance(text) + 14, metrics.height() + 6)
        y = anchor.y() - box.height() - 6
        box.moveTo(anchor.x() - 1, y if y >= 0 else anchor.y() + 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.S500))
        p.drawRoundedRect(box, 2, 2)
        p.setPen(QColor(theme.G950))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_hint(self, p: QPainter, text: str) -> None:
        p.setFont(theme.font(13, 500))
        metrics = p.fontMetrics()
        key_font = theme.font(11, 500, mono=True)
        key = "Esc"
        key_w = 30
        box = QRectF(0, 0, metrics.horizontalAdvance(text) + key_w + 40, 34)
        box.moveCenter(QPointF(self.width() / 2, 44))
        p.setPen(QPen(QColor(theme.G700), 1))
        p.setBrush(QColor(theme.G900))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor(theme.PAPER))
        p.drawText(box.adjusted(16, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        kbox = QRectF(box.right() - key_w - 12, box.center().y() - 9, key_w, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.G700))
        p.drawRoundedRect(kbox, 2, 2)
        p.setFont(key_font)
        p.setPen(QColor(theme.A200))
        p.drawText(kbox, Qt.AlignmentFlag.AlignCenter, key)

    def _draw_loupe(self, p: QPainter, pos: QPointF) -> None:
        """Lupa junto ao cursor: pixels ampliados, posição física e a cor do ponto."""
        center = self.pixel_at(pos)
        half = LOUPE_PX // 2
        source = QRect(center.x() - half, center.y() - half, LOUPE_PX, LOUPE_PX)
        size = LOUPE_PX * LOUPE_ZOOM
        info_h = 24
        x, y = pos.x() + 22, pos.y() + 22
        if x + size > self.width():
            x = pos.x() - 22 - size
        if y + size + info_h > self.height():
            y = pos.y() - 22 - size - info_h
        lens = QRectF(x, y, size, size)

        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.G900))
        p.drawRoundedRect(lens.adjusted(-3, -3, 3, 3 + info_h), 4, 4)
        p.setClipRect(lens)
        p.fillRect(lens, QColor(theme.G950))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        visible = source.intersected(self._image.rect())
        if not visible.isEmpty():
            target = QRectF(lens.left() + (visible.left() - source.left()) * LOUPE_ZOOM,
                            lens.top() + (visible.top() - source.top()) * LOUPE_ZOOM,
                            visible.width() * LOUPE_ZOOM, visible.height() * LOUPE_ZOOM)
            p.drawImage(target, self._image, QRectF(visible))
        grid = QPen(QColor(0, 0, 0, 28), 1)
        p.setPen(grid)
        for i in range(1, LOUPE_PX):
            p.drawLine(QPointF(lens.left() + i * LOUPE_ZOOM, lens.top()), QPointF(lens.left() + i * LOUPE_ZOOM, lens.bottom()))
            p.drawLine(QPointF(lens.left(), lens.top() + i * LOUPE_ZOOM), QPointF(lens.right(), lens.top() + i * LOUPE_ZOOM))
        cross = QColor(theme.S500)
        cross.setAlpha(90)
        mid = half * LOUPE_ZOOM
        p.fillRect(QRectF(lens.left() + mid, lens.top(), LOUPE_ZOOM, size), cross)
        p.fillRect(QRectF(lens.left(), lens.top() + mid, size, LOUPE_ZOOM), cross)
        p.setPen(QPen(QColor(theme.S500), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(lens.left() + mid, lens.top() + mid, LOUPE_ZOOM, LOUPE_ZOOM))
        p.setClipping(False)
        p.setPen(QPen(QColor(theme.G600), 1))
        p.drawRect(lens)

        color = self._image.pixelColor(center) if self._image.rect().contains(center) else QColor("black")
        info = QRectF(lens.left(), lens.bottom() + 3, size, info_h - 3)
        p.setFont(theme.font(10.5, 500, mono=True))
        p.setPen(QColor(theme.A100))
        label = f"Copiado {self._picked}" if self._picked else f"x {center.x()}  y {center.y()}"
        p.drawText(info.adjusted(2, 0, -20, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
        chip = QRectF(info.right() - 15, info.center().y() - 6.5, 13, 13)
        p.setPen(QPen(QColor(theme.G600), 1))
        p.setBrush(color)
        p.drawRoundedRect(chip, 2, 2)
        p.restore()


class CaptureSession(QObject):
    """Abre um overlay por monitor e entrega a primeira seleção concluída."""

    finished = Signal(object, object)  # Action, Selection
    cancelled = Signal()

    def __init__(self, shots: list[ScreenShot], direct_action: Action | None = None):
        super().__init__()
        self._overlays = [SelectionOverlay(shot, direct_action) for shot in shots]
        for overlay in self._overlays:
            overlay.selected.connect(self._on_selected)
            overlay.cancelled.connect(self._on_cancelled)
            overlay.selectionStarted.connect(lambda o=overlay: self._clear_others(o))

    def start(self) -> None:
        for overlay in self._overlays:
            overlay.show()
        # Foca o overlay do monitor onde está o cursor.
        cursor_screen = QGuiApplication.screenAt(QCursor.pos())
        for overlay in self._overlays:
            if overlay.screen() is cursor_screen:
                overlay.activateWindow()

    @property
    def overlays(self) -> list[SelectionOverlay]:
        return list(self._overlays)

    def _clear_others(self, active: SelectionOverlay) -> None:
        for overlay in self._overlays:
            if overlay is not active:
                overlay.clear_selection()

    def _close_all(self) -> None:
        for overlay in self._overlays:
            overlay.close()
        self._overlays.clear()

    def _on_selected(self, action: Action, selection: Selection) -> None:
        self._close_all()
        self.finished.emit(action, selection)

    def _on_cancelled(self) -> None:
        self._close_all()
        self.cancelled.emit()
