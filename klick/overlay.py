"""Overlay fullscreen onde o usuário arrasta o retângulo de seleção.

Um overlay por monitor, cada um mostrando a imagem congelada daquele monitor.
A seleção fica restrita a um monitor por vez.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QGuiApplication, QImage, QKeySequence, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from klick.actions import Action
from klick.capture import ScreenShot, to_physical

ACCENT = QColor("#3b82f6")
DIM = QColor(0, 0, 0, 120)
MIN_SIZE = 3  # seleções menores que isso são tratadas como clique

TOOLBAR_STYLE = """
QFrame#toolbar { background: #1f2937; border: 1px solid #374151; border-radius: 6px; }
QToolButton { color: #f9fafb; background: transparent; border: none; padding: 5px 10px; border-radius: 4px; }
QToolButton:hover { background: #374151; }
QToolButton:pressed { background: #4b5563; }
"""


class Toolbar(QFrame):
    triggered = Signal(object)  # Action
    closeRequested = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setStyleSheet(TOOLBAR_STYLE)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self._add(layout, "Copiar", "Copiar para a área de transferência (Ctrl+C / Enter)",
                  lambda: self.triggered.emit(Action.COPY))
        self._add(layout, "Salvar", "Salvar em arquivo (Ctrl+S)", lambda: self.triggered.emit(Action.SAVE))
        self._add(layout, "✕", "Cancelar (Esc)", self.closeRequested.emit)
        self.adjustSize()
        self.hide()

    @staticmethod
    def _add(layout: QHBoxLayout, text: str, tip: str, slot) -> None:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.clicked.connect(slot)
        layout.addWidget(button)


class SelectionOverlay(QWidget):
    selected = Signal(object, QImage)  # Action, imagem recortada
    cancelled = Signal()
    selectionStarted = Signal()

    def __init__(self, shot: ScreenShot, direct_action: Action | None = None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self._image = shot.image
        self._direct_action = direct_action
        self._selection = QRectF()
        self._origin = QPointF()
        self._drag: str | None = None  # "create" | "move"

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
        self._selection = QRectF()
        self._toolbar.hide()
        self.update()

    def cropped(self) -> QImage:
        rect = to_physical(self._selection, self.size(), self._image.size())
        return self._image.copy(rect)

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

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or event.matches(QKeySequence.StandardKey.Copy):
            self._finish(Action.COPY)
        elif event.matches(QKeySequence.StandardKey.Save):
            self._finish(Action.SAVE)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.position()
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
        if self._drag == "create":
            self._selection = QRectF(self._origin, pos).normalized()
        elif self._drag == "move":
            rect = QRectF(self._selection)
            rect.moveTopLeft(pos - self._origin)
            self._selection = self._keep_inside(rect)
        else:
            inside = self._has_selection() and self._selection.contains(event.position())
            self.setCursor(Qt.CursorShape.SizeAllCursor if inside else Qt.CursorShape.CrossCursor)
            return
        self.update()

    def mouseReleaseEvent(self, event) -> None:
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
        p.fillPath(dim, DIM)

        if self._has_selection():
            pen = QPen(ACCENT, 1)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawRect(self._selection)
            phys = to_physical(self._selection, self.size(), self._image.size())
            self._draw_label(p, f"{phys.width()} × {phys.height()}", self._selection.topLeft())
        elif self._drag is None:
            self._draw_hint(p, "Arraste para selecionar  ·  Esc para sair")

    # --- internos ----------------------------------------------------------

    def _finish(self, action: Action) -> None:
        if self._has_selection():
            self.selected.emit(action, self.cropped())

    def _has_selection(self) -> bool:
        return self._selection.width() >= MIN_SIZE and self._selection.height() >= MIN_SIZE

    def _clamp(self, pos: QPointF) -> QPointF:
        return QPointF(min(max(pos.x(), 0), self.width()), min(max(pos.y(), 0), self.height()))

    def _keep_inside(self, rect: QRectF) -> QRectF:
        x = min(max(rect.x(), 0), self.width() - rect.width())
        y = min(max(rect.y(), 0), self.height() - rect.height())
        rect.moveTo(x, y)
        return rect

    def _place_toolbar(self) -> None:
        tb = self._toolbar
        tb.adjustSize()
        gap = 6
        sel = self._selection
        x = sel.right() - tb.width()
        y = sel.bottom() + gap
        if y + tb.height() > self.height():
            y = sel.top() - tb.height() - gap
        if y < 0:
            y = sel.bottom() - tb.height() - gap
        x = min(max(x, 0), self.width() - tb.width())
        tb.move(round(x), round(y))
        tb.show()
        tb.raise_()

    def _draw_label(self, p: QPainter, text: str, anchor: QPointF) -> None:
        font = QFont(self.font())
        font.setPointSizeF(9)
        p.setFont(font)
        metrics = p.fontMetrics()
        box = QRectF(0, 0, metrics.horizontalAdvance(text) + 12, metrics.height() + 6)
        y = anchor.y() - box.height() - 4
        box.moveTo(anchor.x(), y if y >= 0 else anchor.y() + 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(17, 24, 39, 220))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor("#f9fafb"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_hint(self, p: QPainter, text: str) -> None:
        font = QFont(self.font())
        font.setPointSizeF(10)
        p.setFont(font)
        metrics = p.fontMetrics()
        box = QRectF(0, 0, metrics.horizontalAdvance(text) + 24, metrics.height() + 12)
        box.moveCenter(QPointF(self.width() / 2, 40 + box.height() / 2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(17, 24, 39, 200))
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor("#f9fafb"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)


class CaptureSession(QObject):
    """Abre um overlay por monitor e entrega a primeira seleção concluída."""

    finished = Signal(object, QImage)  # Action, imagem
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

    def _on_selected(self, action: Action, image: QImage) -> None:
        self._close_all()
        self.finished.emit(action, image)

    def _on_cancelled(self) -> None:
        self._close_all()
        self.cancelled.emit()
