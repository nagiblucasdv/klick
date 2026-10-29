"""Moldura e controles exibidos enquanto a área está sendo gravada.

Ficam do lado de fora da área e, no Windows, também são excluídos da captura
(SetWindowDisplayAffinity), então não aparecem no vídeo.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QRect, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from klick import config, icons, theme
from klick.widgets import Panel, Segmented, button

BORDER = 2
CORNER = 14
WDA_EXCLUDEFROMCAPTURE = 0x11


def exclude_from_capture(widget: QWidget) -> None:
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE)


class RecordingFrame(QWidget):
    """Moldura vermelha com cantos de visor em volta da área, que não recebe cliques."""

    def __init__(self, area: QRect):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        pad = BORDER + 2
        self.setGeometry(area.adjusted(-pad, -pad, pad, pad))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        exclude_from_capture(self)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(BORDER, BORDER, -BORDER, -BORDER)
        p.setPen(QPen(QColor(theme.REC), 1))
        p.drawRect(r)
        pen = QPen(QColor(theme.REC), BORDER * 2)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        p.setPen(pen)
        for x, dx in ((r.left(), CORNER), (r.right(), -CORNER)):
            for y, dy in ((r.top(), CORNER), (r.bottom(), -CORNER)):
                p.drawLine(int(x), int(y), int(x + dx), int(y))
                p.drawLine(int(x), int(y), int(x), int(y + dy))


class RecordingControls(Panel):
    """HUD: ponto REC, tempo, tamanho e Parar. Ao gerar o GIF vira uma barra de progresso."""

    stopRequested = Signal()

    def __init__(self, area: QRect, elapsed, label: str = "MP4"):
        super().__init__()
        self._elapsed = elapsed
        self._dot_on = True
        self._busy = False
        self._phase = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(30, 6, 6, 6)
        layout.setSpacing(12)
        self._time = QLabel("00:00")
        self._time.setFont(theme.font(15, 600, mono=True))
        self._meta = QLabel(f"{area.width()} × {area.height()} · {label}")
        self._meta.setFont(theme.font(11, 400, mono=True))
        self._meta.setStyleSheet(f"color: {theme.G400};")
        self._stop = button("Parar", "secondary")
        self._stop.setIcon(icons.icon("stop", theme.REC, size=16))
        self._stop.setToolTip(theme.tip("Parar a gravação", "Ctrl ⇧ R"))
        self._stop.clicked.connect(self.stopRequested.emit)
        layout.addWidget(self._time)
        layout.addWidget(self._meta)
        layout.addWidget(self._stop)
        self.adjustSize()
        self._place(area)

        self._timer = QTimer(self, interval=500, timeout=self._tick)
        self._timer.start()
        self._spin = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1200, loopCount=-1)
        self._spin.valueChanged.connect(self._on_spin)

    def set_status(self, text: str) -> None:
        self._timer.stop()
        self._busy = True
        self._time.setText(text)
        self._time.setFont(theme.font(13, 600))
        self._meta.setText("")
        self._stop.hide()
        self.setMinimumWidth(self.width())
        self._spin.start()
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        exclude_from_capture(self)

    def _tick(self) -> None:
        seconds = int(self._elapsed())
        self._time.setText(f"{seconds // 60:02d}:{seconds % 60:02d}")
        self._dot_on = not self._dot_on
        self.update()

    def _on_spin(self, value) -> None:
        self._phase = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self.height() / 2
        color = QColor(theme.S500 if self._busy else theme.REC)
        halo = QColor(color)
        halo.setAlpha(60)
        p.setPen(Qt.PenStyle.NoPen)
        if self._busy or self._dot_on:
            p.setBrush(halo)
            p.drawEllipse(QRectF(9, cy - 8, 16, 16))
            p.setBrush(color)
            p.drawEllipse(QRectF(12, cy - 5, 10, 10))
        if self._busy:
            # barra indeterminada: um trecho laranja correndo no trilho
            track = QRectF(self._time.geometry().right() + 14, cy - 2, max(60, self.width() - self._time.geometry().right() - 28), 4)
            p.setBrush(QColor(theme.G700))
            p.drawRoundedRect(track, 2, 2)
            seg = track.width() * 0.35
            x = track.left() + (track.width() + seg) * self._phase - seg
            p.setClipRect(track)
            p.setBrush(QColor(theme.S500))
            p.drawRoundedRect(QRectF(x, track.top(), seg, track.height()), 2, 2)

    def _place(self, area: QRect) -> None:
        screen = QGuiApplication.screenAt(area.center()) or QGuiApplication.primaryScreen()
        bounds = screen.availableGeometry()
        gap = BORDER + 8
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

    def __init__(self, area: QRect, elapsed, label: str = "MP4"):
        self.frame = RecordingFrame(area)
        self.controls = RecordingControls(area, elapsed, label)
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


SOUND_OPTIONS = [("none", "Sem som"), ("system", "Do computador"), ("mic", "Microfone"), ("both", "Os dois")]
SOUND_HINTS = {
    "none": "Vídeo mudo",
    "system": "O que toca nos alto-falantes ou fones",
    "mic": "Sua voz, pelo microfone padrão do Windows",
    "both": "Computador e microfone misturados",
}


class RecordSetup(QFrame):
    """Antes de gravar: vai ter som? qual qualidade? Fica ao lado da seleção, no overlay."""

    startRequested = Signal(str, str)  # qualidade, som
    backRequested = Signal()

    def __init__(self, parent: QWidget, gif: bool):
        super().__init__(parent)
        from klick.recorder import QUALITIES

        self._qualities = QUALITIES
        self._gif = gif
        self.setObjectName("panel")
        self.setStyleSheet(theme.dark_panel_stylesheet())
        self.setCursor(Qt.CursorShape.ArrowCursor)
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        dot = QLabel()
        dot.setPixmap(icons.pixmap("gif" if gif else "rec", theme.S500 if gif else theme.REC, 18))
        title = QLabel("Gravar GIF" if gif else "Gravar vídeo")
        title.setFont(theme.font(15, 750, 112))
        head.addWidget(dot)
        head.addWidget(title)
        head.addStretch(1)
        col.addLayout(head)

        self.sound = Segmented(SOUND_OPTIONS, config.record_audio())
        self._sound_hint = QLabel()
        self._sound_hint.setProperty("role", "muted")
        self._sound_hint.setFont(theme.font(11.5, 400))
        self.sound.changed.connect(lambda key: self._sound_hint.setText(SOUND_HINTS[key]))
        self._sound_hint.setText(SOUND_HINTS[self.sound.value])
        if not gif:
            col.addWidget(self._section("VAI TER SOM?"))
            col.addWidget(self.sound)
            col.addWidget(self._sound_hint)

        self.quality = Segmented([(k, q.label) for k, q in QUALITIES.items()], config.record_quality())
        self._quality_hint = QLabel()
        self._quality_hint.setProperty("role", "muted")
        self._quality_hint.setFont(theme.font(11.5, 400))
        self.quality.changed.connect(self._show_quality)
        self._show_quality(self.quality.value)
        col.addWidget(self._section("QUALIDADE"))
        col.addWidget(self.quality)
        col.addWidget(self._quality_hint)

        foot = QHBoxLayout()
        foot.setSpacing(6)
        back = button("Voltar", "ghost")
        back.setToolTip(theme.tip("Voltar à seleção", "Esc"))
        back.clicked.connect(self.backRequested.emit)
        self.start = button("Iniciar gravação", "danger", "rec")
        self.start.setIcon(icons.icon("rec", "#ffffff", size=16))
        self.start.setStyleSheet(f"QPushButton {{ background: {theme.REC}; color: #ffffff; border-color: {theme.REC}; }}"
                                 "QPushButton:hover { background: #ff5a50; }")
        self.start.setToolTip(theme.tip("Começar a gravar", "Enter"))
        self.start.clicked.connect(self.accept)
        foot.addWidget(back)
        foot.addStretch(1)
        foot.addWidget(self.start)
        col.addSpacing(4)
        col.addLayout(foot)
        self.adjustSize()

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "section")
        return label

    def _show_quality(self, key: str) -> None:
        q = self._qualities[key]
        self._quality_hint.setText(f"{q.gif_fps} fps · até {q.gif_width} px de largura" if self._gif else q.hint)

    def accept(self) -> None:
        """Começa a gravar com o que está escolhido e guarda como padrão da próxima vez."""
        sound = "none" if self._gif else self.sound.value
        config.set_record_quality(self.quality.value)
        if not self._gif:
            config.set_record_audio(sound)
        self.startRequested.emit(self.quality.value, sound)
