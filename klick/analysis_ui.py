"""Janela da Análise: um print de consulta SQL, JSON ou grade de resultado, pronto para usar.

O Klick decide o tipo e mostra só essa visão ("Ler como" troca se ele errar). Cada correção do OCR fica
marcada com uma ondinha no texto, pisca uma vez quando chega e aparece na lista ao lado, de onde dá
para desfazer. À direita, a conclusão diz em uma frase o que aquilo é e a conferência aponta o que
pode estar errado.

Lê com os dois motores (o RapidOCR em modo código e o do Windows) e fica com a leitura mais limpa;
uma leitura melhor que chega depois só entra se você ainda não editou nada.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future
from contextlib import contextmanager
from html import escape

from PySide6.QtCore import QRect, QRectF, QRegularExpression, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (QColor, QFont, QImage, QKeySequence, QPainter, QShortcut, QSyntaxHighlighter,
                           QTextCharFormat, QTextCursor, QTextFormat)
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPlainTextEdit, QScrollArea, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from klick import analysis, config, ocr, theme
from klick.actions import copy_text, store_text
from klick.analysis import Kind, document, fixes, grid, query
from klick.analysis.fixes import SQL_KEYWORDS
from klick.analysis.layout import layout_text
from klick.icon import app_icon
from klick.ocr import OcrResult
from klick.widgets import Pena, Segmented, Switch, button

log = logging.getLogger(__name__)

SIDE = 340
PRINT = 220
KINDS = [(Kind.SQL.value, "SQL"), (Kind.JSON.value, "JSON"), (Kind.TABLE.value, "Tabela"), (Kind.TEXT.value, "Texto")]
TITLES = {Kind.SQL: "Consulta SQL", Kind.JSON: "JSON", Kind.TABLE: "Tabela", Kind.TEXT: "Texto"}
FORMATS = [("excel", "Excel"), ("csv", "CSV"), ("markdown", "Markdown"), ("insert", "INSERT"), ("update", "UPDATE"),
           ("json", "JSON")]
EXTENSIONS = {"excel": "txt", "csv": "csv", "markdown": "md", "insert": "sql", "update": "sql", "json": "json"}
STRING, NUMBER = "#9a5b00", "#1c6fb8"


# --- editor de código --------------------------------------------------------------------

def _format(color: str, bold: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.DemiBold)
    return f


class Highlighter(QSyntaxHighlighter):
    """Cores do SQL (palavras-chave, textos, números, comentários) ou do JSON (chaves, textos, números)."""

    def __init__(self, document, language: str):
        super().__init__(document)
        self.language = language
        self._rules = {
            "sql": [(QRegularExpression(r"\b\d+(\.\d+)?\b"), _format(NUMBER)),
                    (QRegularExpression(r"\b(" + "|".join(sorted(SQL_KEYWORDS)) + r")\b",
                                        QRegularExpression.PatternOption.CaseInsensitiveOption),
                     _format(theme.ACCENT_TEXT, True)),
                    (QRegularExpression(r"'[^']*'"), _format(STRING)),
                    (QRegularExpression(r"--[^\n]*|/\*.*?\*/"), _format(theme.FAINT))],
            "json": [(QRegularExpression(r'"(?:[^"\\]|\\.)*"'), _format(STRING)),
                     (QRegularExpression(r"-?\b\d+(\.\d+)?([eE][+-]?\d+)?\b"), _format(NUMBER)),
                     (QRegularExpression(r"\b(true|false|null)\b"), _format(theme.REC, True)),
                     (QRegularExpression(r'"(?:[^"\\]|\\.)*"(?=\s*:)'), _format(theme.ACCENT_TEXT, True))],
        }

    def highlightBlock(self, text: str) -> None:
        for pattern, form in self._rules.get(self.language, []):
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), form)


class _Gutter(QWidget):
    def __init__(self, editor: "CodeEdit"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_gutter(event)


class CodeEdit(QPlainTextEdit):
    """Editor de código com número das linhas, as correções do OCR marcadas (piscam ao chegar) e a linha do erro."""

    def __init__(self, language: str = "", read_only: bool = False):
        super().__init__()
        self.setFont(theme.font(13.5, mono=True))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setReadOnly(read_only)
        self.highlighter = Highlighter(self.document(), language)
        self._gutter = _Gutter(self)
        self._marks: list[tuple[int, int]] = []
        self._error_line = 0
        self._glow = 0.0
        self._flash = QVariantAnimation(self, startValue=1.0, endValue=0.0, duration=theme.ms(1600))
        self._flash.valueChanged.connect(self._on_flash)
        self.blockCountChanged.connect(lambda _: self._fit_gutter())
        self.updateRequest.connect(self._scroll_gutter)
        self._fit_gutter()

    def gutter_width(self) -> int:
        return 18 + self.fontMetrics().horizontalAdvance("9") * max(2, len(str(self.blockCount())))

    def _fit_gutter(self) -> None:
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _scroll_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        r = self.contentsRect()
        self._gutter.setGeometry(QRect(r.left(), r.top(), self.gutter_width(), r.height()))

    def paint_gutter(self, event) -> None:
        p = QPainter(self._gutter)
        p.fillRect(event.rect(), QColor(theme.PAGE))
        p.setFont(theme.font(12, mono=True))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            number = block.blockNumber() + 1
            p.setPen(QColor(theme.REC if number == self._error_line else theme.FAINT))
            p.drawText(0, top, self._gutter.width() - 10, height, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       str(number))
            block = block.next()
            top += height

    def set_marks(self, marks: list[tuple[int, int]], flash: bool = True) -> None:
        """Trechos (início, fim) corrigidos pelo OCR: ondinha embaixo; ao chegar, um fundo que se apaga."""
        self._marks = marks
        if flash and marks and self._flash.duration():
            self._flash.stop()
            self._flash.start()
        else:
            self._glow = 0.0
            self._apply()

    def set_error_line(self, line: int) -> None:
        self._error_line = line
        self._apply()
        self._gutter.update()

    def _on_flash(self, value) -> None:
        self._glow = float(value)
        self._apply()

    def _apply(self) -> None:
        selections = []
        if self._error_line:
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor(theme.DANGER_BG))
            sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = QTextCursor(self.document().findBlockByNumber(self._error_line - 1))
            selections.append(sel)
        size = len(self.toPlainText())
        for start, end in self._marks:
            if end > size:
                continue
            sel = QTextEdit.ExtraSelection()
            sel.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            sel.format.setUnderlineColor(QColor(theme.SIGNAL))
            if self._glow > 0:
                glow = QColor(theme.SIGNAL)
                glow.setAlpha(round(90 * self._glow))
                sel.format.setBackground(glow)
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cursor
            selections.append(sel)
        self.setExtraSelections(selections)


# --- print com a linha de leitura ----------------------------------------------------------

class ShotView(QWidget):
    """O print em miniatura; enquanto lê, uma linha com o brilho da pena desce por ele."""

    def __init__(self, image: QImage):
        super().__init__()
        self.image = image
        scale = min((PRINT - 28) / max(1, image.width()), 240 / max(1, image.height()), 1.0)
        self.setFixedSize(max(40, round(image.width() * scale)), max(30, round(image.height() * scale)))
        self._scan = -1.0
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1300, loopCount=-1)
        self._anim.valueChanged.connect(self._on_scan)

    def reading(self, on: bool) -> None:
        if on and theme.motion():
            self._anim.start()
        else:
            self._anim.stop()
            self._scan = -1.0
            self.update()

    def _on_scan(self, value) -> None:
        self._scan = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        p.drawImage(r, self.image)
        p.setPen(QColor(theme.PENA_LINE))
        p.drawRect(r.adjusted(0, 0, -1, -1))
        if self._scan >= 0:
            y = r.height() * self._scan
            band = QColor(theme.SIGNAL)
            band.setAlpha(40)
            p.fillRect(QRectF(0, y - 16, r.width(), 16), band)
            p.fillRect(QRectF(0, y - 1, r.width(), 2), theme.sheen(r))


# --- painel da direita ------------------------------------------------------------------------

def _drop(item) -> None:
    """Tira um item de um layout: o widget some na hora (o deleteLater só apaga depois)."""
    if item is not None and item.widget() is not None:
        item.widget().hide()
        item.widget().deleteLater()


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(theme.font(15, 600, display=True))
    return label


def _text(text: str = "", muted: bool = False, mono: bool = False) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setFont(theme.font(12.5, mono=mono) if mono else theme.font(13.5))
    if muted:
        label.setProperty("role", "muted")
    return label


class Verdict(QFrame):
    """A conclusão: uma frase, num cartão com o fio de brilho da pena à esquerda."""

    def __init__(self):
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(16, 12, 14, 12)
        col.setSpacing(4)
        col.addWidget(_heading("Conclusão"))
        self.text = _text()
        self.text.setFont(theme.font(14))
        col.addWidget(self.text)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        r = QRectF(self.rect())
        p.fillRect(r, QColor(theme.SURFACE))
        p.setPen(QColor(theme.LINE))
        p.drawRect(r.adjusted(0, 0, -1, -1))
        p.fillRect(QRectF(0, 0, 3, r.height()), theme.sheen(QRectF(0, 0, r.height(), 3)))


class Checks(QWidget):
    """A conferência: uma linha por aviso, com a bolinha da gravidade."""

    COLORS = {"danger": theme.REC, "warn": theme.WARN, "ok": theme.OK}

    def __init__(self):
        super().__init__()
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(0, 0, 0, 0)
        self._col.setSpacing(6)

    def set_checks(self, checks: list[query.Check]) -> None:
        while self._col.count():
            _drop(self._col.takeAt(0))
        for check in checks:
            row = QLabel(f"<span style='color:{self.COLORS[check.level]}; font-size:15px'>●</span>&nbsp; "
                         f"{escape(check.text)}")
            row.setWordWrap(True)
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setFont(theme.font(13))
            if check.level == "danger":
                row.setStyleSheet(f"background: {theme.DANGER_BG}; border: 1px solid {theme.DANGER_LINE};"
                                  f" border-radius: 3px; padding: 6px 8px;")
            self._col.addWidget(row)


class FixList(QWidget):
    """O que foi corrigido do OCR: "FR0M → FROM" com o botão de desfazer cada um."""

    undo = Signal(int)  # número do conserto

    def __init__(self):
        super().__init__()
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(0, 0, 0, 0)
        self._col.setSpacing(4)
        self.locked = False  # o usuário editou: desfazer voltaria o texto todo

    def set_fixes(self, found: list[fixes.Fix], undone: int = 0) -> None:
        while self._col.count():
            _drop(self._col.takeAt(0))
        if not found and not undone:
            self._col.addWidget(_text("Nada: a leitura veio limpa.", muted=True))
            return
        for fix in found:
            row = QHBoxLayout()
            before = escape(fix.before.replace("\n", " ")) or "∅"
            after = escape(fix.after.replace("\n", " ")) or "(apagado)"
            label = QLabel(f"<span style='color:{theme.FAINT}'><s>{before}</s></span>&nbsp;&nbsp;→&nbsp;&nbsp;"
                           f"<b>{after}</b>")
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setFont(theme.font(12.5, mono=True))
            row.addWidget(label, 1)
            back = button("Desfazer", "ghost")
            back.setFixedHeight(26)
            back.setEnabled(not self.locked)
            back.setToolTip("Voltar ao que o OCR leu neste ponto" if not self.locked
                            else "Você já editou o texto: desfazer apagaria a sua edição")
            back.clicked.connect(lambda _=False, n=fix.number: self.undo.emit(n))
            row.addWidget(back)
            box = QWidget()
            box.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            self._col.addWidget(box)
        if undone:
            self._col.addWidget(_text(f"{undone} desfeito{'s' if undone != 1 else ''}.", muted=True))


class Parts(QWidget):
    """Partes da consulta em duas colunas: o nome e o conteúdo."""

    def __init__(self):
        super().__init__()
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(0, 0, 0, 0)
        self._col.setSpacing(6)

    def set_parts(self, parts: list[tuple[str, str]]) -> None:
        while self._col.count():
            _drop(self._col.takeAt(0))
        for name, value in parts:
            if not value:
                continue
            row = QHBoxLayout()
            row.setSpacing(10)
            key = _text(name, muted=True)
            key.setFixedWidth(78)
            key.setAlignment(Qt.AlignmentFlag.AlignTop)
            row.addWidget(key)
            row.addWidget(_text(value, mono=True), 1)
            box = QWidget()
            row.setContentsMargins(0, 0, 0, 0)
            box.setLayout(row)
            self._col.addWidget(box)


def _inspector(*rows: QWidget) -> QScrollArea:
    inner = QWidget()
    inner.setObjectName("inspector")
    inner.setStyleSheet("QWidget#inspector { background: transparent; }")
    col = QVBoxLayout(inner)
    col.setContentsMargins(16, 16, 16, 16)
    col.setSpacing(10)
    for row in rows:
        col.addWidget(row)
    col.addStretch(1)
    scroll = QScrollArea()
    scroll.setWidget(inner)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.viewport().setAutoFillBackground(False)
    return scroll


def _section(title: str, body: QWidget) -> QWidget:
    box = QWidget()
    col = QVBoxLayout(box)
    col.setContentsMargins(0, 6, 0, 0)
    col.setSpacing(6)
    col.addWidget(_heading(title))
    col.addWidget(body)
    return box


# --- janela -------------------------------------------------------------------------------------

class AnalysisWindow(QWidget):
    recognized = Signal(str)  # o texto lido (já corrigido), para guardar na galeria
    finished = Signal(str)  # o texto final, ao fechar (com as suas edições)
    readRequested = Signal()  # "Abrir na leitura" (texto comum)
    _done = Signal(object, str)  # resultado, erro (vem das threads do OCR)

    def __init__(self, image: QImage, result: OcrResult | None = None, kind: Kind | str | None = None,
                 refine: bool = True, schema=None):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("window")
        self.setWindowTitle("Klick: análise")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(theme.window_stylesheet() + f"""
            QWidget#center {{ background: {theme.PAGE}; }}
            QWidget#side {{ background: {theme.SURFACE}; border-left: 1px solid {theme.LINE}; }}
            QTableWidget {{ background: {theme.FIELD}; color: {theme.INK}; border: 1px solid {theme.LINE};
                border-radius: {theme.RADIUS}px; gridline-color: {theme.LINE}; selection-background-color: {theme.ACCENT_SOFT};
                selection-color: {theme.ACCENT_TEXT}; }}
            QHeaderView::section {{ background: {theme.PAGE}; color: {theme.MUTED}; border: none;
                border-right: 1px solid {theme.LINE}; border-bottom: 1px solid {theme.LINE}; padding: 5px 8px;
                font-family: '{theme.DISPLAY}'; font-size: 12px; }}
            QTableCornerButton::section {{ background: {theme.PAGE}; border: none; }}
            QTreeWidget {{ background: {theme.FIELD}; border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px; }}
            QTreeWidget::item {{ padding: 3px 2px; }}
            QTreeWidget::item:selected {{ background: {theme.ACCENT_SOFT}; color: {theme.ACCENT_TEXT}; }}
            QLabel#tile {{ background: {theme.SURFACE}; border: 1px solid {theme.LINE}; border-radius: 3px; padding: 8px 12px; }}
            QLabel#chipOk {{ background: {theme.ACCENT_SOFT}; color: {theme.ACCENT_TEXT}; border-radius: 3px; padding: 3px 9px; }}
            QLabel#chipBad {{ background: {theme.DANGER_BG}; color: {theme.DANGER_FG}; border-radius: 3px; padding: 3px 9px; }}""")
        self.resize(1260, 760)
        self._image = image
        self._schema = schema
        self._raw = ""  # o texto como a leitura montou (com a indentação do print)
        self._result: OcrResult | None = None
        self._kind: Kind = Kind(kind) if kind else Kind.SQL
        self._forced = kind is not None  # veio escolhido (da leitura): não troca sozinho
        self._sql_skip: frozenset[int] = frozenset()
        self._json_skip: frozenset[int] = frozenset()
        self._sql_fixes: list[fixes.Fix] = []
        self._query: query.Query | None = None
        self._filling = False
        self._touched = False
        self._candidates: list[OcrResult] = []
        self._pending = 0
        self._reported = False

        # --- coluna do print, na pena ---
        left = Pena()
        left.setFixedWidth(PRINT)
        lcol = QVBoxLayout(left)
        lcol.setContentsMargins(14, 16, 14, 14)
        lcol.setSpacing(10)
        brand = QLabel("Análise")
        brand.setFont(theme.font(22, 600, display=True))
        lcol.addWidget(brand)
        self.shot = ShotView(image)
        lcol.addWidget(self.shot, 0, Qt.AlignmentFlag.AlignHCenter)
        self.engine = QLabel("Lendo…")
        self.engine.setWordWrap(True)
        self.engine.setProperty("role", "muted")
        self.engine.setFont(theme.font(12.5))
        size = QLabel(f"Print de {image.width()} × {image.height()} px")
        size.setProperty("role", "muted")
        size.setFont(theme.font(12.5))
        lcol.addWidget(self.engine)
        lcol.addWidget(size)
        lcol.addStretch(1)

        # --- centro: tipo, a visão do tipo e as ações ---
        center = QWidget(objectName="center")
        ccol = QVBoxLayout(center)
        ccol.setContentsMargins(20, 14, 20, 14)
        ccol.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(10)
        self.title = QLabel(TITLES[self._kind])
        self.title.setFont(theme.font(26, 600, display=True))
        self.subtitle = QLabel("")
        self.subtitle.setProperty("role", "muted")
        self.subtitle.setFont(theme.font(13.5))
        read_as = QLabel("Ler como")
        read_as.setProperty("role", "muted")
        self.kinds = Segmented(KINDS, self._kind.value)
        self.kinds.setToolTip("Se o Klick errou o tipo, troque aqui")
        self.kinds.changed.connect(lambda value: self._set_kind(Kind(value), user=True))
        head.addWidget(self.title)
        head.addWidget(self.subtitle, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        head.addWidget(read_as)
        head.addWidget(self.kinds)
        ccol.addLayout(head)

        self.pages = QStackedWidget()
        self.inspectors = QStackedWidget()
        self._build_sql()
        self._build_json()
        self._build_table()
        self._build_text()
        ccol.addWidget(self.pages, 1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.message = QLabel("")
        self.message.setProperty("role", "muted")
        self.message.setWordWrap(True)
        self.save = button("Salvar arquivo", "ghost", "save")
        self.save.setToolTip("Salvar na pasta Leitura")
        self.save.clicked.connect(self._save)
        self.copy = button("Copiar", "primary", "copy")
        self.copy.setToolTip(theme.tip("Copiar", "Ctrl Enter"))
        self.copy.clicked.connect(self._copy)
        foot.addWidget(self.message, 1)
        foot.addWidget(self.save)
        foot.addWidget(self.copy)
        ccol.addLayout(foot)

        side = QWidget(objectName="side")
        side.setFixedWidth(SIDE)
        scol = QVBoxLayout(side)
        scol.setContentsMargins(0, 0, 0, 0)
        scol.addWidget(self.inspectors)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(left)
        layout.addWidget(center, 1)
        layout.addWidget(side)

        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._copy)
        self._done.connect(self._on_done)
        self._set_kind(self._kind)

        # Os dois motores; fica a leitura mais limpa (o RapidOCR em modo código costuma ganhar, mas às vezes
        # perde uma linha inteira, e aí o do Windows salva).
        futures = []
        if refine or result is None:
            if config.option("precise_ocr") and ocr.precise_available():
                futures.append(ocr.recognize_precise(image, code=True))
            futures.append(ocr.recognize_words(image, config.ocr_language()))
        self._pending = len(futures)
        self.shot.reading(bool(futures))
        if result is not None:
            self._take(result, "")
        for future in futures:
            future.add_done_callback(self._emit_done)

    # --- montagem ----------------------------------------------------------------------------

    def _page(self, *rows) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        for row in rows:
            if isinstance(row, QHBoxLayout):
                col.addLayout(row)
            else:
                col.addWidget(row, 1 if isinstance(row, (CodeEdit, QSplitter, QTableWidget)) else 0)
        return page

    def _build_sql(self) -> None:
        self.sql_view = Segmented([("formatted", "Formatado"), ("raw", "Como estava")], "formatted")
        self.sql_view.changed.connect(lambda _: self._render_sql())
        self.preview = button("SELECT de conferência", "secondary", "search")
        self.preview.setToolTip("Copia um SELECT com as linhas que o comando vai mudar, para conferir antes de rodar")
        self.preview.clicked.connect(lambda: self._copy_text(query.preview_select(self._query), "SELECT de conferência copiado"))
        self.backup = button("Backup antes", "secondary", "save")
        self.backup.setToolTip("Copia um CREATE TABLE … AS SELECT com as linhas que vão mudar, para voltar se der errado")
        self.backup.clicked.connect(lambda: self._copy_text(query.backup_select(self._query), "Backup copiado"))
        row = QHBoxLayout()
        row.addWidget(self.sql_view)
        row.addStretch(1)
        row.addWidget(self.preview)
        row.addWidget(self.backup)
        self.sql = CodeEdit("sql")
        self.sql.setPlaceholderText("A consulta aparece aqui assim que a leitura terminar")
        self.sql.textChanged.connect(self._on_sql_edited)
        self.pages.addWidget(self._page(row, self.sql))

        self.sql_verdict = Verdict()
        self.sql_parts = Parts()
        self.sql_checks = Checks()
        self.sql_fix_list = FixList()
        self.sql_fix_list.undo.connect(self._undo_sql)
        self.inspectors.addWidget(_inspector(self.sql_verdict, _section("Partes", self.sql_parts),
                                             _section("Conferência", self.sql_checks),
                                             _section("Corrigido do OCR", self.sql_fix_list)))

    def _build_json(self) -> None:
        pretty = button("Formatar", "secondary", "json")
        pretty.clicked.connect(lambda: self._format_json(compact=False))
        small = button("Compactar", "ghost")
        small.setToolTip("Tudo numa linha, para colar em log ou requisição")
        small.clicked.connect(lambda: self._format_json(compact=True))
        self.as_table = button("Ver como tabela", "secondary", "table")
        self.as_table.setToolTip("A lista de objetos vira uma grade: copie como Excel, INSERT…")
        self.as_table.clicked.connect(self._json_to_table)
        row = QHBoxLayout()
        row.addWidget(pretty)
        row.addWidget(small)
        row.addStretch(1)
        row.addWidget(self.as_table)
        self.json = CodeEdit("json")
        self.json.setPlaceholderText("O JSON aparece aqui assim que a leitura terminar")
        self.json.textChanged.connect(self._on_json_edited)
        self._json_timer = QTimer(self, singleShot=True, interval=300, timeout=self._update_json)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Campo", "Valor"])
        self.tree.setFont(theme.font(13))
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setToolTip("Clique copia o caminho (itens[0].cod); duplo clique copia o valor")
        self.tree.itemClicked.connect(lambda item: self._copy_text(item.data(0, Qt.ItemDataRole.UserRole),
                                                                   f"Caminho copiado: {item.data(0, Qt.ItemDataRole.UserRole)}"))
        self.tree.itemDoubleClicked.connect(lambda item: self._copy_text(item.data(1, Qt.ItemDataRole.UserRole),
                                                                         "Valor copiado"))
        split = QSplitter()
        split.addWidget(self.json)
        split.addWidget(self.tree)
        split.setSizes([520, 300])
        self.pages.addWidget(self._page(row, split))

        self.json_verdict = Verdict()
        self.json_state = QLabel("—")
        self.json_state.setFont(theme.font(13, 600, display=True))
        self.json_error = _text(muted=True)
        state = QWidget()
        state_col = QVBoxLayout(state)
        state_col.setContentsMargins(0, 0, 0, 0)
        state_col.addWidget(self.json_state, 0, Qt.AlignmentFlag.AlignLeft)
        state_col.addWidget(self.json_error)
        self.json_size = _text(mono=True)
        self.json_fix_list = FixList()
        self.json_fix_list.undo.connect(self._undo_json)
        self.inspectors.addWidget(_inspector(self.json_verdict, _section("Situação", state),
                                             _section("Tamanho", self.json_size),
                                             _section("Corrigido do OCR", self.json_fix_list)))

    def _build_table(self) -> None:
        self.tiles = QHBoxLayout()
        self.tiles.setSpacing(8)
        self.table_name = QLineEdit(placeholderText="nome da tabela")
        self.table_name.setAccessibleName("Nome da tabela")
        self.table_name.setFixedWidth(190)
        self.table_name.textChanged.connect(self._update_output)
        self.header = Switch(True)
        self.header.setAccessibleName("Primeira linha é o cabeçalho")
        self.header.toggled.connect(self._on_header)
        self.comma = Switch(True)
        self.comma.setAccessibleName("Vírgula decimal")
        self.comma.toggled.connect(self._update_output)
        remove = button("Apagar linhas", "ghost", "trash")
        remove.setToolTip("Apagar as linhas selecionadas da grade (Del)")
        remove.clicked.connect(self._remove_rows)
        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(self.table_name)
        controls.addSpacing(8)
        controls.addWidget(self.header)
        controls.addWidget(QLabel("1ª linha é cabeçalho"))
        controls.addSpacing(8)
        controls.addWidget(self.comma)
        comma_label = QLabel("Vírgula decimal")
        comma_label.setToolTip("1.240,50 vira 1240.50 no SQL e conta como número")
        controls.addWidget(comma_label)
        controls.addStretch(1)
        controls.addWidget(remove)

        self.grid = QTableWidget()
        self.grid.setFont(theme.font(13))
        self.grid.verticalHeader().setDefaultSectionSize(28)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.grid.horizontalHeader().setStretchLastSection(True)
        self.grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.grid.itemChanged.connect(self._on_cell)
        QShortcut(QKeySequence.StandardKey.Delete, self.grid, activated=self._remove_rows)

        self.format = Segmented(FORMATS, "excel")
        self.format.changed.connect(self._update_output)
        self.key = QComboBox()
        self.key.setAccessibleName("Coluna do WHERE")
        self.key.currentIndexChanged.connect(self._update_output)
        self._key_label = QLabel("WHERE")
        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        out_row.addWidget(QLabel("Copiar como"))
        out_row.addWidget(self.format)
        out_row.addWidget(self._key_label)
        out_row.addWidget(self.key)
        out_row.addStretch(1)
        self.output = CodeEdit("sql", read_only=True)
        self.output.setFont(theme.font(12.5, mono=True))
        self.output.setMaximumHeight(170)
        page = self._page(self.tiles, controls, self.grid, out_row, self.output)
        self.pages.addWidget(page)

        self.table_verdict = Verdict()
        self.columns_info = QLabel()
        self.columns_info.setWordWrap(True)
        self.columns_info.setTextFormat(Qt.TextFormat.RichText)
        self.columns_info.setFont(theme.font(13))
        self.suspects = _text()
        self.apply_suspects = button("Trocar pelas sugestões", "secondary", "check")
        self.apply_suspects.clicked.connect(self._apply_suspects)
        suspects = QWidget()
        scol = QVBoxLayout(suspects)
        scol.setContentsMargins(0, 0, 0, 0)
        scol.addWidget(self.suspects)
        scol.addWidget(self.apply_suspects, 0, Qt.AlignmentFlag.AlignLeft)
        self._suspects_box = _section("Células suspeitas", suspects)
        copy_summary = button("Copiar resumo", "ghost", "sum")
        copy_summary.clicked.connect(lambda: self._copy_text(self.summary_text(), "Resumo copiado"))
        self.inspectors.addWidget(_inspector(self.table_verdict, self._suspects_box,
                                             _section("Colunas", self.columns_info), copy_summary))
        self._suspected: dict[tuple[int, int], str] = {}

    def _build_text(self) -> None:
        self.plain = CodeEdit()
        self.plain.setFont(theme.font(14))
        self.plain.textChanged.connect(self._on_edit)
        self.pages.addWidget(self._page(self.plain))
        self.text_verdict = Verdict()
        open_reader = button("Abrir na leitura", "secondary", "read")
        open_reader.clicked.connect(self.readRequested.emit)
        self.inspectors.addWidget(_inspector(self.text_verdict, open_reader))

    # --- leitura -------------------------------------------------------------------------------

    def _emit_done(self, future: Future) -> None:
        try:
            self._done.emit(future.result(), "")
        except Exception as exc:  # noqa: BLE001 - qualquer falha do OCR vira mensagem na janela
            log.warning("Leitura da análise falhou", exc_info=exc)
            self._done.emit(None, str(exc) or type(exc).__name__)

    def _on_done(self, result: OcrResult | None, error: str) -> None:
        self._pending = max(0, self._pending - 1)
        self._take(result, error)

    def _take(self, result: OcrResult | None, error: str) -> None:
        """Mais uma leitura pronta: mostra a melhor até agora (se você ainda não editou)."""
        if result is not None and result.words:
            self._candidates.append(result)
        best = max(self._candidates, key=lambda r: analysis.reading_score(layout_text(r)), default=None)
        if not self._pending:
            self.shot.reading(False)
        if best is None:
            if not self._pending:
                self.engine.setText("Não foi possível ler.")
                self.message.setText(error or "Nenhum texto encontrado nesta área.")
            return
        if best is not self._result:
            if self._result is not None and self._touched:
                self.message.setText("Saiu uma leitura melhor, mas você já editou: mantive o seu texto.")
            else:
                self._load(best)
        engine = "RapidOCR, modo código" if best.language == "RapidOCR" else "OCR do Windows"
        others = len(self._candidates) - 1
        self.engine.setText(f"Leitura: {engine}, {len(best.words)} palavras"
                            + (". Conferindo com o outro motor…" if self._pending else
                               f". Escolhida entre {others + 1} leituras." if others else "."))
        if not self._pending and not self._reported:
            self._reported = True
            self.recognized.emit(self.current_text())

    def _load(self, result: OcrResult) -> None:
        self._result = result
        self._raw = layout_text(result)
        self._sql_skip = self._json_skip = frozenset()
        if not self._forced:
            self._kind = analysis.detect(result) or Kind.TEXT
        with self._quiet():
            self._render_sql(flash=self._kind is Kind.SQL)
            self._render_json(flash=self._kind is Kind.JSON)
            self.set_rows(grid.table_rows(result.words))
            self.plain.setPlainText(self._raw)
        self._set_kind(self._kind)

    # --- tipo -------------------------------------------------------------------------------------

    def _set_kind(self, kind: Kind, user: bool = False) -> None:
        self._kind = kind
        if user:
            self._forced = True
        index = [k for k, _ in KINDS].index(kind.value)
        self.pages.setCurrentIndex(index)
        self.inspectors.setCurrentIndex(index)
        if self.kinds.value != kind.value:
            self.kinds.buttons[kind.value].setChecked(True)
        self.title.setText(TITLES[kind])
        self.save.setText({Kind.SQL: "Salvar .sql", Kind.JSON: "Salvar .json", Kind.TEXT: "Salvar .txt"}
                          .get(kind, "Salvar arquivo"))
        self._update_subtitle()
        if kind is Kind.TABLE:
            self._update_output()
        if kind is Kind.TEXT:
            lines = len([line for line in self.plain.toPlainText().splitlines() if line.strip()])
            self.text_verdict.text.setText(
                f"Texto comum, {lines} linha{'s' if lines != 1 else ''}: não parece SQL, JSON nem tabela. "
                "Se for, escolha em Ler como, em cima." if lines else "Nada lido ainda.")

    def _update_subtitle(self) -> None:
        if self._kind is Kind.SQL and self._query is not None and self._query.kind:
            extra = " com junção" if self._query.joins else ""
            self.subtitle.setText(f"{self._query.kind}{extra}")
        elif self._kind is Kind.TABLE and self.grid.rowCount():
            self.subtitle.setText(f"{self.grid.rowCount()} × {self.grid.columnCount()}")
        else:
            self.subtitle.setText("")

    # --- SQL ---------------------------------------------------------------------------------

    def _render_sql(self, flash: bool = False) -> None:
        found = fixes.fix_sql(self._raw, self._sql_skip)
        self._sql_fixes = found.fixes
        text = found.text
        marks = [(f.start, f.end) for f in found.fixes if f.after]
        if self.sql_view.value == "formatted" and query.looks_like_sql(found.text):
            text = query.format_sql(found.text)
            marks = self._marks_in(text, [f.after for f in found.fixes if f.after.strip()])
        with self._quiet():
            self.sql.setPlainText(text)
        self.sql.set_marks(marks, flash=flash)
        self.sql_fix_list.set_fixes(found.fixes, len(self._sql_skip))
        self._analyze_sql(found.unclosed)

    @staticmethod
    def _marks_in(text: str, pieces: list[str]) -> list[tuple[int, int]]:
        """Acha cada trecho corrigido no texto formatado, em ordem (a formatação muda as posições)."""
        out, pos, lower = [], 0, text.lower()
        for piece in pieces:
            i = lower.find(piece.lower().strip(), pos)
            if i >= 0:
                out.append((i, i + len(piece.strip())))
                pos = i + len(piece.strip())
        return out

    def _analyze_sql(self, unclosed: str = "") -> None:
        text = self.sql.toPlainText()
        q = query.parse(text)
        self._query = q
        self.sql_verdict.text.setText(query.describe(q) if text.strip() else "Nada lido ainda.")
        order = ", ".join(f"{e}{' (maior primeiro)' if d else ''}" for e, d in q.order)
        joins = "\n".join(f"{j.kind} {j.table}{' ' + j.alias if j.alias else ''}"
                          + (f" ON {j.condition}" if j.condition else "") for j in q.joins)
        tables = ", ".join(f"{t} {a}".strip() for t, a in q.tables)
        self.sql_parts.set_parts([
            ("Tabelas", tables), ("Colunas", "\n".join(q.columns) if q.kind == "SELECT" else ", ".join(q.columns)),
            ("Altera", "\n".join(f"{c} = {v}" for c, v in q.assignments)), ("Junções", joins),
            ("Filtros", "\n".join(q.filters)), ("Agrupa", ", ".join(q.group)), ("Ordem", order), ("Limite", q.limit)])
        self.sql_checks.set_checks(query.checks(q, unclosed) if text.strip() else [])
        guarded = q.kind in ("UPDATE", "DELETE") and bool(q.where)
        self.preview.setVisible(guarded)
        self.backup.setVisible(guarded)
        self._update_subtitle()

    def _on_sql_edited(self) -> None:
        if self._filling:
            return
        self._on_edit()
        self.sql_fix_list.locked = True
        self.sql_fix_list.set_fixes(self._sql_fixes, len(self._sql_skip))
        self.sql.set_marks([], flash=False)
        self._analyze_sql()

    def _undo_sql(self, number: int) -> None:
        self._sql_skip = self._sql_skip | {number}
        self._render_sql()

    # --- JSON -----------------------------------------------------------------------------------

    def _render_json(self, flash: bool = False) -> None:
        text, found = fixes.fix_json(self._raw, self._json_skip)
        reading = document.read(text)
        marks = [(f.start, f.end) for f in found if f.after]
        if reading.ok:
            text = document.pretty(reading.value)
            marks = self._marks_in(text, [f.after for f in found if f.after.strip()])
        with self._quiet():
            self.json.setPlainText(text)
        self.json.set_marks(marks, flash=flash)
        self.json_fix_list.set_fixes(found, len(self._json_skip))
        self._update_json()

    def _on_json_edited(self) -> None:
        if self._filling:
            return
        self._on_edit()
        self.json_fix_list.locked = True
        self.json.set_marks([], flash=False)
        self._json_timer.start()

    def _undo_json(self, number: int) -> None:
        self._json_skip = self._json_skip | {number}
        self._render_json()

    def _update_json(self) -> None:
        text = self.json.toPlainText()
        reading = document.read(text) if text.strip() else document.Reading(error="")
        self.json.set_error_line(reading.line)
        if not text.strip():
            self.json_state.setText("—")
            self.json_state.setObjectName("")
        elif reading.ok:
            self.json_state.setText("Válido")
            self.json_state.setObjectName("chipOk")
        else:
            self.json_state.setText("Inválido")
            self.json_state.setObjectName("chipBad")
        self.json_state.style().unpolish(self.json_state)
        self.json_state.style().polish(self.json_state)
        self.json_error.setText(f"{reading.error[0].upper()}{reading.error[1:]}. A linha fica marcada no texto."
                                if reading.error else "")
        self.json_verdict.text.setText(document.describe(reading) if text.strip() else "Nada lido ainda.")
        self.json_size.setText(f"{reading.keys} chaves\n{reading.items} itens em listas\n{reading.depth} níveis"
                               if reading.ok and text.strip() else "—")
        self.as_table.setVisible(bool(reading.ok and document.records(reading.value)))
        self._fill_tree(reading.value if reading.ok else None)

    def _fill_tree(self, value) -> None:
        self.tree.clear()
        if value is None:
            return

        def add(parent, key, node, parts) -> None:
            item = QTreeWidgetItem(parent)
            item.setText(0, str(key))
            if isinstance(node, (dict, list)):
                item.setText(1, document.type_name(node))
                item.setForeground(1, QColor(theme.MUTED))
                children = node.items() if isinstance(node, dict) else enumerate(node)
                for k, child in list(children)[:500]:
                    add(item, f"[{k}]" if isinstance(node, list) else k, child, [*parts, k])
            else:
                item.setText(1, document.compact(node))
            item.setData(0, Qt.ItemDataRole.UserRole, document.path(parts))
            item.setData(1, Qt.ItemDataRole.UserRole, document.compact(node) if not isinstance(node, str) else node)

        if isinstance(value, (dict, list)):
            children = value.items() if isinstance(value, dict) else enumerate(value)
            for k, child in list(children)[:500]:
                add(self.tree, f"[{k}]" if isinstance(value, list) else k, child, [k])
        else:
            add(self.tree, "$", value, [])
        self.tree.expandToDepth(0)

    def _format_json(self, compact: bool) -> None:
        reading = document.read(self.json.toPlainText())
        if not reading.ok:
            self.message.setText(f"Ainda inválido: {reading.error}.")
            return
        self.json.setPlainText(document.compact(reading.value) if compact else document.pretty(reading.value))
        self.message.setText("")

    def _json_to_table(self) -> None:
        reading = document.read(self.json.toPlainText())
        found = document.records(reading.value) if reading.ok else None
        if not found:
            return
        parts, objects = found
        self.set_rows(document.to_rows(objects))
        self.header.setChecked(True)
        if parts and isinstance(parts[-1], str) and not self.table_name.text():
            self.table_name.setText(parts[-1])
        self._set_kind(Kind.TABLE, user=True)
        self.message.setText(f"{len(objects)} objetos de {document.path(parts)} viraram linhas.")

    # --- tabela ---------------------------------------------------------------------------------

    def set_rows(self, rows: list[list[str]]) -> None:
        with self._quiet():
            width = max((len(r) for r in rows), default=0)
            self.grid.setRowCount(len(rows))
            self.grid.setColumnCount(width)
            for r, row in enumerate(rows):
                for c in range(width):
                    self.grid.setItem(r, c, QTableWidgetItem(row[c] if c < len(row) else ""))
        self.header.blockSignals(True)
        self.header.setChecked(grid.has_header(rows) if rows else True)
        self.header.blockSignals(False)
        self._on_header(self.header.isChecked())

    def rows(self) -> list[list[str]]:
        return [[(self.grid.item(r, c).text() if self.grid.item(r, c) else "") for c in range(self.grid.columnCount())]
                for r in range(self.grid.rowCount())]

    def _on_cell(self, item) -> None:
        if self._filling:
            return
        self._on_edit()
        if item.row() == 0:
            self._refresh_columns()
        self._update_output()

    def _on_header(self, on: bool) -> None:
        bold, normal = theme.font(13, 600), theme.font(13)
        with self._quiet():
            for c in range(self.grid.columnCount()):
                if (item := self.grid.item(0, c)) is not None:
                    item.setFont(bold if on else normal)
        self._refresh_columns()
        self._update_output()

    def _refresh_columns(self) -> None:
        names = grid.columns(self.rows(), self.header.isChecked())
        self.grid.setHorizontalHeaderLabels(names)
        current = self.key.currentIndex()
        self.key.blockSignals(True)
        self.key.clear()
        self.key.addItems(names)
        self.key.setCurrentIndex(min(max(current, 0), len(names) - 1) if names else -1)
        self.key.blockSignals(False)

    def _remove_rows(self) -> None:
        self._on_edit()
        for r in sorted({i.row() for i in self.grid.selectedIndexes()}, reverse=True):
            self.grid.removeRow(r)
        self._refresh_columns()
        self._update_output()

    def table_text(self) -> str:
        rows, fmt = self.rows(), self.format.value
        header, comma, name = self.header.isChecked(), self.comma.isChecked(), self.table_name.text()
        return {
            "excel": lambda: grid.to_tsv(rows),
            "csv": lambda: grid.to_csv(rows),
            "markdown": lambda: grid.to_markdown(rows, header),
            "update": lambda: grid.to_update(rows, name, max(self.key.currentIndex(), 0), header, comma),
            "insert": lambda: grid.to_insert(rows, name, header, comma),
            "json": lambda: grid.to_json(rows, header, comma),
        }[fmt]()

    def stats(self) -> list[grid.ColumnStats]:
        return grid.column_stats(self.rows(), self.header.isChecked(), self.comma.isChecked())

    def summary_text(self) -> str:
        lines = [self.table_verdict.text.text()]
        for c in self.stats():
            line = f"{c.name} ({c.kind}): {c.filled} de {c.total} preenchidos, {c.distinct} diferentes"
            if c.sum is not None:
                line += f"; soma {grid.brl(c.sum)}, média {grid.brl(c.mean)}, de {grid.brl(c.min)} a {grid.brl(c.max)}"
            lines.append(line)
        return "\n".join(lines)

    def _update_output(self, *_) -> None:
        update = self.format.value == "update"
        self._key_label.setVisible(update)
        self.key.setVisible(update)
        self.output.highlighter.language = "json" if self.format.value == "json" else \
            "sql" if self.format.value in ("insert", "update") else ""
        self.output.setPlainText(self.table_text())
        self.output.highlighter.rehighlight()
        self._update_summary()

    def _update_summary(self) -> None:
        rows, header = self.rows(), self.header.isChecked()
        stats = self.stats()
        self.table_verdict.text.setText(grid.describe(rows, header, stats) if rows else "Nada lido ainda.")
        parts = []
        for c in stats:
            head = (f"<b>{escape(c.name)}</b> <span style='color:{theme.MUTED}'>{c.kind}, "
                    f"{c.filled} de {c.total}, {c.distinct} diferentes</span>")
            if c.sum is not None:
                head += (f"<br><span style='color:{theme.ACCENT_TEXT}'>Σ {grid.brl(c.sum)}</span>"
                         f" <span style='color:{theme.MUTED}'>média {grid.brl(c.mean)}, "
                         f"de {grid.brl(c.min)} a {grid.brl(c.max)}</span>")
            parts.append(head)
        self.columns_info.setText("<br><br>".join(parts) or "—")
        # Blocos do topo: o tamanho e até duas somas.
        while self.tiles.count():
            _drop(self.tiles.takeAt(0))
        data = len(grid.data_rows(rows, header))
        tiles = [("Linhas", str(data)), ("Colunas", str(self.grid.columnCount()))]
        tiles += [(f"Soma de {c.name}", grid.brl(c.sum)) for i, c in enumerate(stats)
                  if c.sum is not None and not grid.key_like(c, first=i == 0)][:3]
        for label, value in tiles:
            tile = QLabel(f"<span style='color:{theme.MUTED}; font-size:12px'>{escape(label)}</span><br>"
                          f"<span style='font-family:{theme.DISPLAY}; font-size:20px'>{escape(value)}</span>")
            tile.setObjectName("tile")
            tile.setTextFormat(Qt.TextFormat.RichText)
            self.tiles.addWidget(tile)
        self.tiles.addStretch(1)
        self._mark_suspects(rows, header)
        self._update_subtitle()

    def _mark_suspects(self, rows: list[list[str]], header: bool) -> None:
        self._suspected = grid.suspicious(rows, header) if rows else {}
        with self._quiet():
            for r in range(self.grid.rowCount()):
                for c in range(self.grid.columnCount()):
                    item = self.grid.item(r, c)
                    if item is None:
                        continue
                    guess = self._suspected.get((r, c))
                    item.setBackground(QColor(theme.TEMP_BG) if guess else QColor(0, 0, 0, 0))
                    item.setToolTip(f"O OCR pode ter errado: talvez {guess}" if guess else "")
        self._suspects_box.setVisible(bool(self._suspected))
        self.suspects.setText("\n".join(f"Linha {r + 1}, {grid.columns(rows, header)[c]}: "
                                        f"{rows[r][c]} → {guess}" for (r, c), guess in self._suspected.items()))

    def _apply_suspects(self) -> None:
        with self._quiet():
            for (r, c), guess in self._suspected.items():
                self.grid.item(r, c).setText(guess)
        self._on_edit()
        self._update_output()
        self.message.setText("Células trocadas pelas sugestões.")

    # --- ações ---------------------------------------------------------------------------------

    def _on_edit(self) -> None:
        if not self._filling:
            self._touched = True

    @contextmanager
    def _quiet(self):
        """O programa está preenchendo os campos: nada disso conta como edição sua (pode aninhar)."""
        was, self._filling = self._filling, True
        try:
            yield
        finally:
            self._filling = was

    def current_text(self) -> str:
        if self._kind is Kind.SQL:
            return self.sql.toPlainText()
        if self._kind is Kind.JSON:
            return self.json.toPlainText()
        if self._kind is Kind.TABLE:
            return self.table_text()
        return self.plain.toPlainText()

    def _copy_text(self, text: str, message: str = "Copiado") -> None:
        if not text or not text.strip():
            return
        copy_text(text)
        self.message.setText(message)

    def _copy(self) -> None:
        text = self.current_text()
        if not text.strip():
            return
        self._copy_text(text, "Copiado")
        self._learn()
        label = self.copy.text()
        self.copy.setText("Copiado")
        QTimer.singleShot(1400, self.copy, lambda: self.copy.setText(label))

    def _learn(self) -> None:
        """Copiou ou salvou: a consulta (ou a grade com nome de tabela) ensina a estrutura das tabelas."""
        if self._schema is None or not config.option("structure"):
            return
        if self._kind is Kind.SQL and self.sql.toPlainText().strip():
            self._schema.learn_query(self.sql.toPlainText())
        elif self._kind is Kind.TABLE and self.table_name.text().strip() and self.header.isChecked():
            self._schema.learn_columns(self.table_name.text(), grid.columns(self.rows(), True))

    def _save(self) -> None:
        text = self.current_text()
        if not text.strip():
            return
        ext = {Kind.SQL: "sql", Kind.JSON: "json", Kind.TEXT: "txt"}.get(self._kind) or EXTENSIONS[self.format.value]
        try:
            path = store_text(text, ext)
        except OSError as exc:
            self.message.setText(f"Não deu para salvar: {exc}")
            return
        self._learn()
        self.message.setText(f"Salvo em Leitura/{path.name}")

    def closeEvent(self, event) -> None:
        if self._reported:
            self.finished.emit(self.current_text())
        super().closeEvent(event)
