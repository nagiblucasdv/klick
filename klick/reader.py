"""Leitura: o print aberto com o texto reconhecido, para escolher o trecho como no Google Lens.

A imagem escurece e só o texto fica aceso. Arraste sobre as palavras para selecionar
(a seleção segue a ordem de leitura), duplo clique pega a linha, Ctrl+A tudo, Ctrl+C copia.
Ao lado, o texto reconhecido dá para corrigir antes de copiar.

O resultado do Windows aparece na hora; o do RapidOCR, mais preciso, chega de 1 a 4 s
depois e toma o lugar dele (a menos que você já tenha corrigido o texto à mão).
"""

from __future__ import annotations

import logging
from concurrent.futures import Future

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QKeySequence, QPainter, QPainterPath, QPen, QShortcut,
                           QTextCursor)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QSizePolicy, QVBoxLayout, QWidget

from klick import config, lens, ocr, sql, theme
from klick.actions import copy_text, store_text
from klick.icon import app_icon
from klick.ocr import OcrResult
from klick.widgets import button

log = logging.getLogger(__name__)

MAX_UPSCALE = 2.0  # prints pequenos ficam maiores para dar para mirar nas palavras
SCAN_MS_PER_WORD = 12
PANEL_WIDTH = 320
DIM = QColor(18, 17, 16, 120)  # escurecimento fora do texto


class WordView(QWidget):
    """Mostra a imagem com o texto aceso; seleciona palavras por arraste."""

    selectionChanged = Signal()

    def __init__(self, image: QImage, scale: float):
        super().__init__()
        self.image = image
        self.scale = scale
        self.result: OcrResult | None = None
        self.message = ""
        self.anchor: int | None = None
        self.focus: int | None = None
        self.hover: int | None = None
        self._lit = 0.0  # quantas palavras já acenderam (animação de leitura)
        self._scan = 0.0  # posição da linha de varredura enquanto lê
        self._dim: QPainterPath | None = None
        self._dim_lit = -1
        self.setFixedSize(QSize(round(image.width() * scale), round(image.height() * scale)))
        self.setMouseTracking(True)
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
        self.anchor = self.focus = self.hover = None
        self.message = "" if result.words else "Nenhum texto encontrado nesta área"
        self._dim = None
        self._lighter.stop()
        self._lit = 0.0
        self._lighter.setEndValue(float(len(result.words)))
        self._lighter.setDuration(min(600, SCAN_MS_PER_WORD * len(result.words)) or 1)
        self._lighter.start()
        self.update()
        self.selectionChanged.emit()

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

    def _box(self, i: int, pad: float = 3) -> QRectF:
        r = self.result.words[i].rect
        return QRectF(r.x() * self.scale - pad, r.y() * self.scale - pad,
                      r.width() * self.scale + 2 * pad, r.height() * self.scale + 2 * pad)

    def word_at(self, pos: QPointF, nearest: bool = False) -> int | None:
        if not self.result:
            return None
        best, best_d = None, None
        for i in range(len(self.result.words)):
            box = self._box(i, 4)
            if box.contains(pos):
                return i
            if nearest:
                dx = max(box.left() - pos.x(), 0, pos.x() - box.right())
                dy = max(box.top() - pos.y(), 0, pos.y() - box.bottom())
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
        pos = event.position()
        if event.buttons() & Qt.MouseButton.LeftButton and self.anchor is not None:
            i = self.word_at(pos, nearest=True)
            if i is not None and i != self.focus:
                self.select(self.anchor, i)
            return
        hover = self.word_at(pos)
        if hover != self.hover:
            self.hover = hover
            self.setCursor(Qt.CursorShape.IBeamCursor if hover is not None else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event) -> None:
        self.hover = None
        self.update()

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

    def _dim_path(self) -> QPainterPath:
        """Tudo menos as palavras já acesas (recalcula só quando acende mais alguma)."""
        lit = min(len(self.result.words), int(self._lit + 0.999))
        if self._dim is None or lit != self._dim_lit:
            words = QPainterPath()
            words.setFillRule(Qt.FillRule.WindingFill)
            for i in range(lit):
                words.addRoundedRect(self._box(i), 3, 3)
            full = QPainterPath()
            full.addRect(QRectF(self.rect()))
            self._dim = full.subtracted(words) if lit else full
            self._dim_lit = lit
        return self._dim

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

        if self.result and self.result.words:
            p.fillPath(self._dim_path(), DIM)
            rng = self.selected_range()
            fill = QColor(theme.S500)
            fill.setAlpha(80)
            for i in range(len(self.result.words)):
                box = self._box(i)
                if rng and rng[0] <= i <= rng[1]:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(fill)
                    p.drawRoundedRect(box, 3, 3)
                    p.fillRect(QRectF(box.left() + 2, box.bottom() - 2.5, box.width() - 4, 2.5), QColor(theme.S500))
                elif i == self.hover:
                    p.setPen(QPen(QColor(255, 255, 255, 190), 1.5))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(box, 3, 3)

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
    """Janela da leitura. Roda o OCR sozinha (rápido e depois o preciso) e avisa quando terminou."""

    recognized = Signal(object)  # OcrResult final
    _done = Signal(object, str, bool)  # resultado, erro, preciso? (vem das threads do OCR)

    def __init__(self, image: QImage, result: OcrResult | None = None):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("window")
        self.setWindowTitle("Klick: leitura")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        scheme = theme.window_scheme()
        self.setStyleSheet(theme.window_stylesheet(scheme) + f"""
            QPlainTextEdit {{ background: {scheme.field}; color: {scheme.fg}; border: 1px solid {scheme.line};
                border-radius: 3px; padding: 8px; selection-background-color: {theme.S500};
                selection-color: {theme.G950}; }}
            QPlainTextEdit:focus {{ border-color: {theme.S500}; }}""")
        self._precise_done = False
        self._edited = False
        self._syncing = False
        self._offsets: list[tuple[int, int]] = []
        self._image = image
        self._dark = scheme.dark

        screen = QGuiApplication.primaryScreen().availableGeometry()
        ratio = QGuiApplication.primaryScreen().devicePixelRatio()
        natural = (MAX_UPSCALE if image.width() < 500 else 1.0) / ratio
        scale = min(natural, (screen.width() * 0.8 - PANEL_WIDTH) / image.width(),
                    screen.height() * 0.7 / image.height())
        self.view = WordView(image, scale)
        self.view.selectionChanged.connect(self._on_view_selection)

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
        head.addWidget(hint)

        frame = QWidget()
        frame.setStyleSheet(f"background: {theme.G950}; border-radius: 3px;")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(self.view, 0, Qt.AlignmentFlag.AlignCenter)

        side = QVBoxLayout()
        side.setSpacing(6)
        side_title = QLabel("Texto reconhecido")
        side_title.setFont(theme.font(13, 650))
        self.sql_toggle = button("SQL", "ghost", "sql")
        self.sql_toggle.setToolTip("Abrir a consulta na janela de SQL")
        self.sql_toggle.clicked.connect(lambda: self._open_sql("query"))
        self.sql_toggle.hide()
        self.table = button("Tabela", "ghost", "table")
        self.table.setToolTip("Abrir a grade na janela de SQL: Excel, CSV, INSERT ou UPDATE")
        self.table.clicked.connect(lambda: self._open_sql("table"))
        self.table.hide()
        self._sql_windows: list = []
        title_row = QHBoxLayout()
        title_row.addWidget(side_title)
        title_row.addStretch(1)
        title_row.addWidget(self.table)
        title_row.addWidget(self.sql_toggle)
        side_hint = QLabel("Dá para corrigir aqui antes de copiar")
        side_hint.setProperty("role", "muted")
        side_hint.setFont(theme.font(12))
        self.text = QPlainTextEdit()
        self.text.setFont(theme.font(13.5, 450))
        self.text.setPlaceholderText("O texto aparece aqui assim que a leitura terminar")
        self.text.setFixedWidth(PANEL_WIDTH)
        self.text.textChanged.connect(self._on_text_edited)
        self.text.selectionChanged.connect(self._on_text_selection)
        side.addLayout(title_row)
        side.addWidget(side_hint)
        side.addWidget(self.text, 1)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(frame, 1, Qt.AlignmentFlag.AlignTop)
        body.addLayout(side)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.picked = QLabel("Nada selecionado ainda")
        self.picked.setProperty("role", "muted")
        self.picked.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lens = button("Google Lens", "ghost", "lens")
        self.lens.setToolTip("Pesquisar esta imagem no Google Lens")
        self.lens.clicked.connect(lambda: lens.search_image(self._image))
        self.search = button("Pesquisar", "ghost", "globe")
        self.search.setToolTip("Pesquisar o trecho selecionado (ou tudo) no Google")
        self.search.clicked.connect(lambda: lens.search_text(self._selection_text() or self.text.toPlainText()))
        self.save_txt = button("Salvar .txt", "ghost", "save")
        self.save_txt.setToolTip("Salvar o texto na pasta Leitura")
        self.save_txt.clicked.connect(self._save_text)
        self.copy_all = button("Copiar tudo", "secondary")
        self.copy_all.clicked.connect(lambda: self._copy(self.text.toPlainText(), self.copy_all))
        self.copy_sel = button("Copiar seleção", "primary", "copy")
        self.copy_sel.clicked.connect(lambda: self._copy(self._selection_text(), self.copy_sel))
        self.copy_all.setEnabled(False)
        self.copy_sel.setEnabled(False)
        self.search.setEnabled(False)
        self.save_txt.setEnabled(False)
        foot.addWidget(self.picked, 1)
        foot.addWidget(self.lens)
        foot.addWidget(self.search)
        foot.addWidget(self.save_txt)
        foot.addWidget(self.copy_all)
        foot.addWidget(self.copy_sel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)
        layout.addLayout(head)
        layout.addLayout(body, 1)
        layout.addLayout(foot)

        QShortcut(QKeySequence.StandardKey.SelectAll, self.view, activated=self.view.select_all)
        QShortcut(QKeySequence.StandardKey.Copy, self.view, activated=self._copy_shortcut)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        self._done.connect(self._on_done)

        if result is not None:
            self._precise_done = True
            self._on_done(result, "", True)
        else:
            language = config.ocr_language()
            ocr.recognize_words(image, language).add_done_callback(lambda f: self._emit_done(f, False))
            if config.option("precise_ocr") and ocr.precise_available():
                ocr.recognize_precise(image).add_done_callback(lambda f: self._emit_done(f, True))
            else:
                self._precise_done = True

    # --- resultados --------------------------------------------------------

    def _emit_done(self, future: Future, precise: bool) -> None:
        try:
            self._done.emit(future.result(), "", precise)
        except Exception as exc:  # noqa: BLE001 - qualquer falha do OCR vira mensagem na janela
            log.warning("Leitura %s falhou", "precisa" if precise else "rápida", exc_info=exc)
            self._done.emit(None, str(exc) or type(exc).__name__, precise)

    def _on_done(self, result: OcrResult | None, error: str, precise: bool) -> None:
        if precise:
            self._precise_done = True
        elif self._precise_done and self.view.result is not None:
            return  # o preciso chegou antes; o rápido não serve mais

        if error or result is None:
            if self.view.result is None and self._precise_done:
                self.status.setText("Não foi possível ler")
                self.view.set_error(error or "Não foi possível ler o texto")
            elif self.view.result is not None:
                self._update_status()
            return
        if precise and self._edited:
            self.status.setText("Leitura precisa pronta, mas você já corrigiu o texto")
            return
        if precise and self.view.result is not None and not result.words and self.view.result.words:
            self._update_status()
            return  # o preciso não achou nada onde o rápido achou: fica o rápido

        self.view.set_result(result)
        self._fill_text(result)
        self._update_status()
        self.copy_all.setEnabled(bool(result.words))
        self.search.setEnabled(bool(result.words))
        self.save_txt.setEnabled(bool(result.words))
        addon = config.option("addon_sql")
        self.sql_toggle.setVisible(addon and sql.looks_like_sql(result.text))
        self.table.setVisible(addon and sql.looks_like_table(sql.table_rows(result.words)))
        if self._precise_done:
            self.recognized.emit(result)

    def _update_status(self) -> None:
        count = len(self.view.result.words) if self.view.result else 0
        words = f"{count} palavra{'s' if count != 1 else ''}"
        if not self._precise_done:
            suffix = " · refinando…"
        elif self.view.result and self.view.result.language == "RapidOCR":
            suffix = " · leitura precisa"
        else:
            suffix = ""
        self.status.setText(words + suffix)

    def _fill_text(self, result: OcrResult) -> None:
        """Texto do painel montado das palavras, guardando onde cada uma começa e termina."""
        self._offsets = []
        parts, pos, line = [], 0, None
        for word in result.words:
            if line is not None:
                sep = " " if word.line == line else "\n"
                parts.append(sep)
                pos += len(sep)
            self._offsets.append((pos, pos + len(word.text)))
            parts.append(word.text)
            pos += len(word.text)
            line = word.line
        self._syncing = True
        self.text.setPlainText("".join(parts))
        self._syncing = False
        self._edited = False

    # --- seleção sincronizada ----------------------------------------------

    def _on_view_selection(self) -> None:
        rng = self.view.selected_range()
        if not self._edited and self._offsets and not self._syncing:
            self._syncing = True
            cursor = self.text.textCursor()
            if rng:
                cursor.setPosition(self._offsets[rng[0]][0])
                cursor.setPosition(self._offsets[rng[1]][1], QTextCursor.MoveMode.KeepAnchor)
            else:
                cursor.clearSelection()
            self.text.setTextCursor(cursor)
            self._syncing = False
        self._show_picked()

    def _on_text_selection(self) -> None:
        if self._syncing or self._edited or not self._offsets:
            self._show_picked()
            return
        cursor = self.text.textCursor()
        if not cursor.hasSelection():
            self._show_picked()
            return
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        hit = [i for i, (a, b) in enumerate(self._offsets) if a < end and b > start]
        self._syncing = True
        self.view.select(hit[0], hit[-1]) if hit else self.view.select(None, None)
        self._syncing = False
        self._show_picked()

    def _on_text_edited(self) -> None:
        if not self._syncing:
            self._edited = True

    def _selection_text(self) -> str:
        cursor = self.text.textCursor()
        if cursor.hasSelection():
            return cursor.selectedText().replace(" ", "\n")  # o Qt usa   entre parágrafos
        return self.view.selected_text()

    def _show_picked(self) -> None:
        text = " ".join(self._selection_text().split())
        self.copy_sel.setEnabled(bool(text))
        self.picked.setText(f"Selecionado: {text}" if text else "Nada selecionado ainda")

    def _open_sql(self, tab: str) -> None:
        from klick.sql_ui import SqlWindow

        window = SqlWindow(self._image, self.view.result, tab)
        window.destroyed.connect(lambda: window in self._sql_windows and self._sql_windows.remove(window))
        self._sql_windows.append(window)
        window.show()
        window.raise_()
        window.activateWindow()

    def _save_text(self) -> None:
        text = self.text.toPlainText()
        if not text.strip():
            return
        try:
            path = store_text(text)
        except OSError as exc:
            self.picked.setText(f"Não deu para salvar: {exc}")
            return
        self.picked.setText(f"Salvo em Leitura/{path.name}")

    def _copy_shortcut(self) -> None:
        self._copy(self._selection_text() or self.text.toPlainText(), self.copy_sel)

    def _copy(self, text: str, source) -> None:
        if not text:
            return
        copy_text(text)
        label = source.text()
        source.setText("Copiado")
        QTimer.singleShot(1400, source, lambda: source.setText(label))
