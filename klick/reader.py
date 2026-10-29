"""Leitura: o print aberto com as palavras reconhecidas, para escolher o trecho como no Google Lens.

Arraste sobre as palavras para selecionar (a seleção segue a ordem de leitura), duplo clique
pega a linha inteira, Ctrl+A tudo, Ctrl+C copia.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from klick import config, ocr, theme
from klick.actions import copy_text
from klick.icon import app_icon
from klick.ocr import OcrResult
from klick.widgets import button

log = logging.getLogger(__name__)

MAX_UPSCALE = 2.0  # prints pequenos ficam maiores para dar para mirar nas palavras
SCAN_MS_PER_WORD = 14


class WordView(QWidget):
    """Mostra a imagem e as caixas das palavras; seleciona por arraste."""

    selectionChanged = Signal()

    def __init__(self, image: QImage, scale: float):
        super().__init__()
        self.image = image
        self.scale = scale
        self.result: OcrResult | None = None
        self.message = ""
        self.anchor: int | None = None
        self.focus: int | None = None
        self._lit = 0.0  # quantas palavras já acenderam (animação de leitura)
        self._scan = 0.0  # posição da linha de varredura enquanto lê
        self.setFixedSize(QSize(round(image.width() * scale), round(image.height() * scale)))
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._scanner = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1100, loopCount=-1)
        self._scanner.valueChanged.connect(self._on_scan)
        self._scanner.start()
        self._lighter = QVariantAnimation(self, startValue=0.0, endValue=1.0)
        self._lighter.valueChanged.connect(self._on_light)

    # --- estado ------------------------------------------------------------

    def set_result(self, result: OcrResult) -> None:
        self._scanner.stop()
        self.result = result
        self.message = "" if result.words else "Nenhum texto encontrado nesta área"
        self._lighter.setEndValue(float(len(result.words)))
        self._lighter.setDuration(min(700, SCAN_MS_PER_WORD * len(result.words)) or 1)
        self._lighter.start()
        self.update()

    def set_error(self, message: str) -> None:
        self._scanner.stop()
        self.message = message
        self.update()

    def select(self, first: int | None, last: int | None) -> None:
        self.anchor, self.focus = first, last
        self.update()
        self.selectionChanged.emit()

    def select_all(self) -> None:
        if self.result and self.result.words:
            self.select(0, len(self.result.words) - 1)

    def selected_range(self) -> tuple[int, int] | None:
        if self.anchor is None or self.focus is None:
            return None
        return min(self.anchor, self.focus), max(self.anchor, self.focus)

    def selected_text(self) -> str:
        rng = self.selected_range()
        return self.result.text_between(*rng) if rng and self.result else ""

    # --- mouse -------------------------------------------------------------

    def word_at(self, pos: QPointF, nearest: bool = False) -> int | None:
        if not self.result:
            return None
        point = QPointF(pos.x() / self.scale, pos.y() / self.scale)
        best, best_d = None, None
        for i, word in enumerate(self.result.words):
            box = word.rect.adjusted(-3, -4, 3, 4)
            if box.contains(point):
                return i
            if nearest:
                dx = max(box.left() - point.x(), 0, point.x() - box.right())
                dy = max(box.top() - point.y(), 0, point.y() - box.bottom())
                d = dx * dx + dy * dy * 4  # prioriza a mesma linha
                if best_d is None or d < best_d:
                    best, best_d = i, d
        return best

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        i = self.word_at(event.position())
        self.select(i, i)

    def mouseMoveEvent(self, event) -> None:
        if not event.buttons() & Qt.MouseButton.LeftButton or self.anchor is None:
            return
        i = self.word_at(event.position(), nearest=True)
        if i is not None and i != self.focus:
            self.select(self.anchor, i)

    def mouseDoubleClickEvent(self, event) -> None:
        i = self.word_at(event.position())
        if i is None or not self.result:
            return
        line = self.result.words[i].line
        same = [n for n, w in enumerate(self.result.words) if w.line == line]
        self.select(same[0], same[-1])

    # --- pintura -----------------------------------------------------------

    def _on_scan(self, value) -> None:
        self._scan = float(value)
        self.update()

    def _on_light(self, value) -> None:
        self._lit = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(self.rect()), self.image)

        if self.result is None and not self.message:
            # Lendo: uma faixa laranja varre o print, como o visor de uma câmera.
            y = self.height() * self._scan
            band = QColor(theme.S500)
            band.setAlpha(40)
            p.fillRect(QRectF(0, y - 18, self.width(), 18), band)
            p.setPen(QPen(QColor(theme.S500), 2))
            p.drawLine(QPointF(0, y), QPointF(self.width(), y))
            return

        if self.result:
            rng = self.selected_range()
            fill = QColor(theme.S500)
            fill.setAlpha(56)
            for i, word in enumerate(self.result.words):
                box = QRectF(word.rect.x() * self.scale - 2, word.rect.y() * self.scale - 2,
                             word.rect.width() * self.scale + 4, word.rect.height() * self.scale + 4)
                if rng and rng[0] <= i <= rng[1]:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(fill)
                    p.drawRoundedRect(box, 2, 2)
                    p.fillRect(QRectF(box.left(), box.bottom() - 2.5, box.width(), 2.5), QColor(theme.S500))
                elif i < self._lit:
                    outline = QColor(theme.S500)
                    outline.setAlpha(110 if i > self._lit - 6 else 70)
                    p.setPen(QPen(outline, 1))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(box, 2, 2)

        if self.message:
            p.setFont(theme.font(13, 600))
            metrics = p.fontMetrics()
            box = QRectF(0, 0, metrics.horizontalAdvance(self.message) + 28, 32)
            box.moveCenter(QPointF(self.width() / 2, self.height() / 2))
            p.setPen(QPen(QColor(theme.G700), 1))
            p.setBrush(QColor(theme.G900))
            p.drawRoundedRect(box, 4, 4)
            p.setPen(QColor(theme.PAPER))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.message)


class ReaderWindow(QWidget):
    """Janela da leitura. Roda o OCR sozinha e avisa quando terminou."""

    recognized = Signal(object)  # OcrResult
    _done = Signal(object, str)  # resultado, erro (vem da thread do OCR)

    def __init__(self, image: QImage, result: OcrResult | None = None):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("window")
        self.setWindowTitle("Klick: leitura")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        scheme = theme.window_scheme()
        self.setStyleSheet(theme.window_stylesheet(scheme))

        screen = QGuiApplication.primaryScreen().availableGeometry()
        ratio = QGuiApplication.primaryScreen().devicePixelRatio()
        natural = (MAX_UPSCALE if image.width() < 500 else 1.0) / ratio
        scale = min(natural, screen.width() * 0.7 / image.width(), screen.height() * 0.62 / image.height())
        self.view = WordView(image, scale)
        self.view.selectionChanged.connect(self._on_selection)

        head = QHBoxLayout()
        head.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(26, 26))
        title = QLabel("Leitura")
        title.setFont(theme.font(18, 800, 125))
        self.status = QLabel("Lendo…")
        self.status.setProperty("role", "muted")
        self.status.setFont(theme.font(11.5, 400, mono=True))
        head.addWidget(logo)
        head.addWidget(title)
        head.addWidget(self.status)
        head.addStretch(1)
        hint = QLabel("Arraste sobre as palavras · duplo clique pega a linha")
        hint.setProperty("role", "muted")
        hint.setFont(theme.font(12))
        head.addWidget(hint)

        frame = QWidget()
        frame.setStyleSheet(f"background: #ffffff; border: 1px solid {scheme.line}; border-radius: 3px;")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(1, 1, 1, 1)
        inner.addWidget(self.view, 0, Qt.AlignmentFlag.AlignCenter)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.picked = QLabel("Nada selecionado ainda")
        self.picked.setProperty("role", "muted")
        self.picked.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.copy_all = button("Copiar tudo", "secondary")
        self.copy_all.clicked.connect(lambda: self._copy(self.view.result.text if self.view.result else "",
                                                         self.copy_all))
        self.copy_sel = button("Copiar seleção", "primary", "copy")
        self.copy_sel.clicked.connect(lambda: self._copy(self.view.selected_text(), self.copy_sel))
        self.copy_all.setEnabled(False)
        self.copy_sel.setEnabled(False)
        foot.addWidget(self.picked, 1)
        foot.addWidget(self.copy_all)
        foot.addWidget(self.copy_sel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)
        layout.addLayout(head)
        layout.addWidget(frame, 1, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(foot)

        QShortcut(QKeySequence.StandardKey.SelectAll, self, activated=self.view.select_all)
        QShortcut(QKeySequence.StandardKey.Copy, self, activated=self._copy_shortcut)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        self.setMinimumWidth(560)
        self._done.connect(self._on_done)

        if result is not None:
            self._on_done(result, "")
        else:
            ocr.recognize_words(image, config.ocr_language()).add_done_callback(self._emit_done)

    def _emit_done(self, future: Future) -> None:
        try:
            self._done.emit(future.result(), "")
        except Exception as exc:  # noqa: BLE001 - qualquer falha do WinRT vira mensagem na janela
            log.warning("Leitura falhou", exc_info=exc)
            self._done.emit(None, str(exc) or type(exc).__name__)

    def _on_done(self, result: OcrResult | None, error: str) -> None:
        if error or result is None:
            self.status.setText("Não foi possível ler")
            self.view.set_error(error or "Não foi possível ler o texto")
            return
        self.view.set_result(result)
        count = len(result.words)
        self.status.setText(f"{count} palavra{'s' if count != 1 else ''}"
                            + (f" · {result.language}" if result.language else ""))
        self.copy_all.setEnabled(bool(count))
        self.recognized.emit(result)

    def _on_selection(self) -> None:
        text = " ".join(self.view.selected_text().split())
        self.copy_sel.setEnabled(bool(text))
        self.picked.setText(f"Selecionado: {text}" if text else "Nada selecionado ainda")

    def _copy_shortcut(self) -> None:
        text = self.view.selected_text() or (self.view.result.text if self.view.result else "")
        self._copy(text, self.copy_sel)

    def _copy(self, text: str, source) -> None:
        if not text:
            return
        copy_text(text)
        label = source.text()
        source.setText("Copiado")
        QTimer.singleShot(1400, source, lambda: source.setText(label))
