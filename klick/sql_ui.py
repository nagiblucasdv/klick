"""Janela de SQL: a consulta ou a grade de resultado lida de um print, pronta para usar.

Duas abas:
- Consulta: o SQL consertado e formatado, colorido, editável; ao lado o tipo, as tabelas
  citadas e o print.
- Tabela: a grade lida, editável, que vira texto para o Excel, CSV, INSERT ou UPDATE
  (com o nome da tabela e a coluna do WHERE), com prévia ao vivo.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPlainTextEdit, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from klick import config, ocr, sql, theme
from klick.actions import copy_text, store_text
from klick.icon import app_icon
from klick.ocr import OcrResult
from klick.widgets import Segmented, Switch, button, thumbnail

log = logging.getLogger(__name__)

SIDE_WIDTH = 260
FORMATS = [("excel", "Excel"), ("csv", "CSV"), ("insert", "INSERT"), ("update", "UPDATE")]
EXTENSIONS = {"query": "sql", "excel": "txt", "csv": "csv", "insert": "sql", "update": "sql"}

EXTRA_STYLE = f"""
QPlainTextEdit {{ background: {theme.G900}; color: {theme.PAPER}; border: 1px solid {theme.G700}; border-radius: 3px;
    padding: 8px; selection-background-color: {theme.S500}; selection-color: {theme.G950}; }}
QPlainTextEdit:focus {{ border-color: {theme.CYAN}; }}
QTableWidget {{ background: {theme.G900}; color: {theme.PAPER}; border: 1px solid {theme.G700}; border-radius: 3px;
    gridline-color: {theme.G700}; selection-background-color: {theme.G700}; selection-color: {theme.DATA}; }}
QHeaderView::section {{ background: {theme.G850}; color: {theme.G400}; border: none; border-right: 1px solid {theme.G700};
    border-bottom: 1px solid {theme.G700}; padding: 4px 6px; font-family: '{theme.MONO}'; font-size: 11px; }}
QTableCornerButton::section {{ background: {theme.G850}; border: none; }}
QComboBox {{ background: {theme.G850}; color: {theme.PAPER}; border: 1px solid {theme.G700}; border-radius: 3px;
    padding: 5px 10px; min-width: 120px; }}
QComboBox QAbstractItemView {{ background: {theme.G900}; color: {theme.PAPER}; selection-background-color: {theme.G700}; }}
QFrame#card {{ background: {theme.G900}; border: 1px solid {theme.G700}; border-radius: {theme.WINDOW_RADIUS}px; }}
"""


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "muted")
    label.setFont(theme.font(10.5, 600, mono=True))
    return label


class SqlWindow(QWidget):
    """Abre direto na aba que faz sentido (consulta ou tabela).

    Lê o print com o RapidOCR em modo código (ampliado, cores invertidas se o fundo for escuro)
    e com o OCR do Windows, e mostra a leitura mais limpa (sql.reading_score). Vindo da
    leitura, mostra na hora o texto que ela já tinha; uma leitura melhor só entra se você
    ainda não editou.
    """

    recognized = Signal(object)  # OcrResult, para guardar na galeria
    _done = Signal(object, str)  # resultado, erro (vem das threads do OCR)

    def __init__(self, image: QImage, result: OcrResult | None = None, tab: str | None = None, refine: bool = True):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("window")
        self.setWindowTitle("Klick: SQL")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(theme.window_stylesheet() + EXTRA_STYLE)
        self.resize(1080, 680)
        self._image = image
        self._original = ""  # texto como foi lido, para voltar depois de formatar
        self._filling = False
        self._touched = False  # o usuário já editou a consulta ou a grade
        self._candidates: list[OcrResult] = []  # leituras prontas (de cada motor)
        self._shown: OcrResult | None = None
        self._pending = 0
        self._emitted = False

        # --- topo ---
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(26, 26))
        title = QLabel("SQL")
        title.setFont(theme.font(26, 700, 120))
        self.status = QLabel("Lendo…")
        self.status.setProperty("role", "data")
        self.status.setFont(theme.font(12, 500, mono=True))
        self.tabs = Segmented([("query", "Consulta"), ("table", "Tabela")], tab or "query")
        self.tabs.changed.connect(self._show_tab)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(logo)
        head.addWidget(title)
        head.addWidget(self.status)
        head.addStretch(1)
        head.addWidget(self.tabs)

        # --- aba Consulta ---
        self.query = QPlainTextEdit()
        self.query.setFont(theme.font(13.5, 450, mono=True))
        self.query.setPlaceholderText("A consulta aparece aqui assim que a leitura terminar")
        self.query.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._highlighter = sql.SqlHighlighter(self.query.document(), True)
        self.query.textChanged.connect(self._update_info)
        self.query.textChanged.connect(self._on_query_edit)
        self.kind = QLabel("—")
        self.kind.setProperty("role", "data")
        self.kind.setFont(theme.font(16, 600, mono=True))
        self.tables = QLabel("—")
        self.tables.setProperty("role", "data")
        self.tables.setFont(theme.font(12.5, 500, mono=True))
        self.tables.setWordWrap(True)
        self.tables.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        shot = QLabel()
        shot.setPixmap(thumbnail(image, SIDE_WIDTH, 150))
        shot.setFixedSize(SIDE_WIDTH, 150)
        shot.setStyleSheet(f"border: 1px solid {theme.G700}; border-radius: 3px;")
        tidy = button("Formatar", "secondary", "sql")
        tidy.setToolTip("Consertar erros do OCR e formatar de novo")
        tidy.clicked.connect(lambda: self.query.setPlainText(sql.tidy(self.query.toPlainText())))
        original = button("Texto lido", "ghost", "undo")
        original.setToolTip("Voltar ao texto como foi lido, sem formatar")
        original.clicked.connect(lambda: self.query.setPlainText(self._original))
        side = QVBoxLayout()
        side.setSpacing(6)
        side.addWidget(_section("TIPO"))
        side.addWidget(self.kind)
        side.addSpacing(8)
        side.addWidget(_section("TABELAS CITADAS"))
        side.addWidget(self.tables)
        side.addSpacing(8)
        side.addWidget(_section("PRINT"))
        side.addWidget(shot)
        side.addSpacing(8)
        side.addWidget(tidy)
        side.addWidget(original)
        side.addStretch(1)
        side_box = QWidget()
        side_box.setFixedWidth(SIDE_WIDTH)
        side_box.setLayout(side)
        query_page = QWidget()
        q_row = QHBoxLayout(query_page)
        q_row.setContentsMargins(0, 0, 0, 0)
        q_row.setSpacing(16)
        q_row.addWidget(self.query, 1)
        q_row.addWidget(side_box)

        # --- aba Tabela ---
        self.table_name = QLineEdit(placeholderText="tabela")
        self.table_name.setAccessibleName("Nome da tabela")
        self.table_name.setFixedWidth(220)
        self.table_name.textChanged.connect(self._update_output)
        self.header = Switch(True)
        self.header.setAccessibleName("Primeira linha é o cabeçalho")
        self.header.toggled.connect(self._on_header)
        self.comma = Switch(True)
        self.comma.setAccessibleName("Vírgula decimal")
        self.comma.toggled.connect(self._update_output)
        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(_section("NOME DA TABELA"))
        controls.addWidget(self.table_name)
        controls.addSpacing(14)
        controls.addWidget(self.header)
        controls.addWidget(QLabel("Primeira linha é o cabeçalho"))
        controls.addSpacing(14)
        controls.addWidget(self.comma)
        comma_label = QLabel("Vírgula decimal (1.240,50 → 1240.50)")
        controls.addWidget(comma_label)
        controls.addStretch(1)
        remove = button("Apagar linhas", "ghost", "trash")
        remove.setToolTip("Apagar as linhas selecionadas da grade (Del)")
        remove.clicked.connect(self._remove_rows)
        controls.addWidget(remove)

        self.grid = QTableWidget()
        self.grid.setFont(theme.font(13, 450))
        self.grid.verticalHeader().setDefaultSectionSize(28)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.grid.horizontalHeader().setStretchLastSection(True)
        self.grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.grid.itemChanged.connect(self._on_cell)
        QShortcut(QKeySequence.StandardKey.Delete, self.grid, activated=self._remove_rows)

        self.format = Segmented(FORMATS, "insert")
        self.format.changed.connect(self._update_output)
        self.key = QComboBox()
        self.key.setAccessibleName("Coluna do WHERE")
        self.key.currentIndexChanged.connect(self._update_output)
        self._key_label = _section("WHERE")
        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        out_row.addWidget(_section("COPIAR COMO"))
        out_row.addWidget(self.format)
        out_row.addSpacing(10)
        out_row.addWidget(self._key_label)
        out_row.addWidget(self.key)
        out_row.addStretch(1)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(theme.font(12.5, 450, mono=True))
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._out_highlighter = sql.SqlHighlighter(self.output.document(), True)
        table_page = QWidget()
        t_col = QVBoxLayout(table_page)
        t_col.setContentsMargins(0, 0, 0, 0)
        t_col.setSpacing(10)
        t_col.addLayout(controls)
        t_col.addWidget(self.grid, 3)
        t_col.addLayout(out_row)
        t_col.addWidget(self.output, 2)

        self.pages = QStackedWidget()
        self.pages.addWidget(query_page)
        self.pages.addWidget(table_page)

        # --- rodapé ---
        self.message = QLabel("")
        self.message.setProperty("role", "muted")
        self.save = button("Salvar arquivo", "ghost", "save")
        self.save.setToolTip("Salvar na pasta Leitura")
        self.save.clicked.connect(self._save)
        self.copy = button("Copiar", "primary", "copy")
        self.copy.setToolTip(theme.tip("Copiar", "Ctrl Enter"))
        self.copy.clicked.connect(self._copy)
        foot = QHBoxLayout()
        foot.addWidget(self.message, 1)
        foot.addWidget(self.save)
        foot.addWidget(self.copy)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)
        layout.addLayout(head)
        layout.addWidget(self.pages, 1)
        layout.addLayout(foot)

        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._copy)
        self._done.connect(self._on_done)
        self._show_tab(self.tabs.value)

        # Lê com os dois motores e fica com a leitura mais limpa: o RapidOCR em modo código
        # costuma ganhar, mas às vezes perde uma linha inteira, e aí o do Windows salva.
        futures = []
        if refine or result is None:
            if config.option("precise_ocr") and ocr.precise_available():
                futures.append(ocr.recognize_precise(image, code=True))
            futures.append(ocr.recognize_words(image, config.ocr_language()))
        self._pending = len(futures)
        if result is not None:
            self._on_done(result, "")
        for future in futures:
            future.add_done_callback(self._emit_done)

    # --- leitura -----------------------------------------------------------

    def _emit_done(self, future: Future) -> None:
        try:
            self._done.emit(future.result(), "")
        except Exception as exc:  # noqa: BLE001 - qualquer falha do OCR vira mensagem na janela
            log.warning("Leitura do SQL falhou", exc_info=exc)
            self._done.emit(None, str(exc) or type(exc).__name__)

    def _on_query_edit(self) -> None:
        if not self._filling:
            self._touched = True

    def _on_done(self, result: OcrResult | None, error: str) -> None:
        """Mais uma leitura pronta: mostra a melhor até agora (se você ainda não editou)."""
        if self.sender() is self:  # veio de um motor (não do resultado entregue pela leitura)
            self._pending = max(0, self._pending - 1)
        if result is not None and result.words:
            self._candidates.append(result)
        best = max(self._candidates, key=lambda r: sql.reading_score(r.text), default=None)
        if best is None:
            if not self._pending:
                self.status.setText("Não foi possível ler")
                self.message.setText(error or "Nenhum texto encontrado nesta área")
            return
        if best is not self._shown:
            if self._shown is not None and self._touched:
                self.message.setText("Saiu uma leitura melhor, mas você já editou: mantive o seu texto")
            else:
                self._show(best)
        size = ""
        rows = self.rows()
        if sql.looks_like_table(rows) and not sql.looks_like_sql(self._shown.text):
            size = f"{len(rows)} × {len(rows[0])}"
        status = " · ".join(p for p in (f"{len(self._shown.words)} palavras", size) if p)
        self.status.setText(status + (" · conferindo…" if self._pending else ""))
        if not self._pending and not self._emitted:
            self._emitted = True
            self.recognized.emit(self._shown)

    def _show(self, result: OcrResult) -> None:
        self._shown = result
        self._original = result.text
        self._filling = True
        self.query.setPlainText(sql.tidy(result.text) if sql.looks_like_sql(result.text) else result.text)
        self._filling = False
        rows = sql.table_rows(result.words)
        self.set_rows(rows)
        if self.tabs.value == "query" and sql.looks_like_table(rows) and not sql.looks_like_sql(result.text):
            self.tabs.set_value("table")  # é grade, não consulta: já abre na tabela

    # --- tabela ------------------------------------------------------------

    def set_rows(self, rows: list[list[str]]) -> None:
        self._filling = True
        width = max((len(r) for r in rows), default=0)
        self.grid.setRowCount(len(rows))
        self.grid.setColumnCount(width)
        for r, row in enumerate(rows):
            for c in range(width):
                self.grid.setItem(r, c, QTableWidgetItem(row[c] if c < len(row) else ""))
        self._filling = False
        self._on_header(self.header.isChecked())

    def rows(self) -> list[list[str]]:
        return [[(self.grid.item(r, c).text() if self.grid.item(r, c) else "") for c in range(self.grid.columnCount())]
                for r in range(self.grid.rowCount())]

    def _on_cell(self, item) -> None:
        if not self._filling:
            self._touched = True
            if item.row() == 0:
                self._refresh_columns()
            self._update_output()

    def _on_header(self, on: bool) -> None:
        bold = theme.font(13, 700)
        normal = theme.font(13, 450)
        self._filling = True
        for c in range(self.grid.columnCount()):
            if (item := self.grid.item(0, c)) is not None:
                item.setFont(bold if on else normal)
        self._filling = False
        self._refresh_columns()
        self._update_output()

    def _refresh_columns(self) -> None:
        names = sql.columns(self.rows(), self.header.isChecked())
        self.grid.setHorizontalHeaderLabels(names)
        current = self.key.currentIndex()
        self.key.blockSignals(True)
        self.key.clear()
        self.key.addItems(names)
        self.key.setCurrentIndex(min(max(current, 0), len(names) - 1) if names else -1)
        self.key.blockSignals(False)

    def _remove_rows(self) -> None:
        self._touched = True
        for r in sorted({i.row() for i in self.grid.selectedIndexes()}, reverse=True):
            self.grid.removeRow(r)
        self._refresh_columns()
        self._update_output()

    def table_text(self) -> str:
        rows, fmt = self.rows(), self.format.value
        header, comma, name = self.header.isChecked(), self.comma.isChecked(), self.table_name.text()
        if fmt == "excel":
            return sql.to_tsv(rows)
        if fmt == "csv":
            return sql.to_csv(rows)
        if fmt == "update":
            return sql.to_update(rows, name, max(self.key.currentIndex(), 0), header, comma)
        return sql.to_insert(rows, name, header, comma)

    def _update_output(self, *_) -> None:
        update = self.format.value == "update"
        self._key_label.setVisible(update)
        self.key.setVisible(update)
        self.output.setPlainText(self.table_text())

    # --- ações -------------------------------------------------------------

    def _show_tab(self, tab: str) -> None:
        self.pages.setCurrentIndex(0 if tab == "query" else 1)
        if tab == "table":
            self._update_output()

    def _update_info(self) -> None:
        text = self.query.toPlainText()
        self.kind.setText(sql.kind(text) or "—")
        found = sql.tables(text)
        self.tables.setText("\n".join(found) if found else "—")

    def current_text(self) -> str:
        return self.query.toPlainText() if self.tabs.value == "query" else self.table_text()

    def _copy(self) -> None:
        text = self.current_text()
        if not text.strip():
            return
        copy_text(text)
        self.message.setText("Copiado")
        label = self.copy.text()
        self.copy.setText("Copiado")
        QTimer.singleShot(1400, self.copy, lambda: self.copy.setText(label))

    def _save(self) -> None:
        text = self.current_text()
        if not text.strip():
            return
        ext = EXTENSIONS["query" if self.tabs.value == "query" else self.format.value]
        try:
            path = store_text(text, ext)
        except OSError as exc:
            self.message.setText(f"Não deu para salvar: {exc}")
            return
        self.message.setText(f"Salvo em Leitura/{path.name}")
