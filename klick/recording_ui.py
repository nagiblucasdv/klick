"""Moldura e controles exibidos enquanto a área está sendo gravada.

Ficam do lado de fora da área e, no Windows, também são excluídos da captura
(SetWindowDisplayAffinity), então não aparecem no vídeo.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from klick.overlay import TOOLBAR_STYLE

RECORDING_RED = QColor("#ef4444")
BORDER = 2
WDA_EXCLUDEFROMCAPTURE = 0x11


def exclude_from_capture(widget: QWidget) -> None:
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE)


class RecordingFrame(QWidget):
    """Borda vermelha em volta da área, que não recebe cliques."""

    def __init__(self, area: QRect):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(area.adjusted(-BORDER, -BORDER, BORDER, BORDER))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        exclude_from_capture(self)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        pen = QPen(RECORDING_RED, BORDER)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        half = BORDER / 2
        p.drawRect(self.rect().toRectF().adjusted(half, half, -half, -half))


class RecordingControls(QFrame):
    stopRequested = Signal()

    def __init__(self, area: QRect, elapsed):
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self._elapsed = elapsed
        self.setObjectName("toolbar")
        self.setStyleSheet(TOOLBAR_STYLE + "QLabel { color: #f9fafb; padding: 0 6px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 4, 4)
        layout.setSpacing(4)
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {RECORDING_RED.name()}; padding: 0;")
        self._time = QLabel("00:00")
        stop = QToolButton()
        stop.setText("■ Parar")
        stop.setToolTip("Parar a gravação (Ctrl+Shift+R)")
        stop.clicked.connect(self.stopRequested.emit)
        layout.addWidget(self._dot)
        layout.addWidget(self._time)
        layout.addWidget(stop)
        self.adjustSize()
        self._place(area)

        self._timer = QTimer(self, interval=500, timeout=self._tick)
        self._timer.start()

    def set_status(self, text: str) -> None:
        self._timer.stop()
        self._time.setText(text)
        self.findChild(QToolButton).setEnabled(False)
        self.adjustSize()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        exclude_from_capture(self)

    def _tick(self) -> None:
        seconds = int(self._elapsed())
        self._time.setText(f"{seconds // 60:02d}:{seconds % 60:02d}")
        self._dot.setVisible(not self._dot.isVisible() if seconds else True)

    def _place(self, area: QRect) -> None:
        screen = QGuiApplication.screenAt(area.center()) or QGuiApplication.primaryScreen()
        bounds = screen.availableGeometry()
        gap = BORDER + 6
        x = area.right() - self.width()
        y = area.bottom() + gap
        if y + self.height() > bounds.bottom():
            y = area.top() - self.height() - gap
        if y < bounds.top():
            y = area.bottom() - self.height() - gap  # sem espaço: fica dentro (e fora do vídeo no Windows)
        x = min(max(x, bounds.left()), bounds.right() - self.width())
        self.move(x, y)


class RecordingIndicator:
    """Agrupa a moldura e os controles de uma gravação."""

    def __init__(self, area: QRect, elapsed):
        self.frame = RecordingFrame(area)
        self.controls = RecordingControls(area, elapsed)
        self.stopRequested = self.controls.stopRequested

    def show(self) -> None:
        self.frame.show()
        self.controls.show()

    def set_status(self, text: str) -> None:
        self.frame.hide()
        self.controls.set_status(text)

    def close(self) -> None:
        self.frame.close()
        self.controls.close()
