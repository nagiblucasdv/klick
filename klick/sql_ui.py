"""Análise: a consulta SQL, o JSON ou a grade de resultado lidos de um print, prontos para usar.

Três abas, cada uma com o painel da direita explicando o que foi lido:
- Consulta: o SQL consertado e formatado; ao lado o tipo, as tabelas, as junções, os
  filtros, o agrupamento e a ordem.
- JSON: consertado, validado (com linha e coluna do erro) e formatado; ao lado as chaves,
  os itens, a profundidade e os campos do primeiro nível.
- Tabela: a grade editável, que vira texto para o Excel, CSV, INSERT ou UPDATE; ao lado o
  resumo de cada coluna (tipo, preenchidos, soma, média, mínimo e máximo).
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import Future
from html import escape

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPlainTextEdit, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from klick import config, ocr, sql, theme
from klick.actions import copy_text, store_text
from klick.icon import app_icon
from klick.ocr import OcrResult
from klick.widgets import Segmented, Switch, button, thumbnail

log = logging.getLogger(__name__)

SIDE_WIDTH = 290
TABS = [("query", "Consulta SQL"), ("json", "JSON"), ("table", "Tabela")]
FORMATS = [("excel", "Excel"), ("csv", "CSV"), ("insert", "INSERT"), ("update", "UPDATE")]
EXTENSIONS = {"query": "sql", "json": "json", "excel": "txt", "csv": "csv", "insert": "sql", "update": "sql"}

EXTRA_STYLE = f"""
QPlainTextEdit {{ background: {theme.G850}; color: {theme.PAPER}; border: 1px solid {theme.G700};
    border-radius: {theme.RADIUS}px; padding: 10px; selection-background-color: {theme.SOFT};
    selection-color: {theme.S600}; }}
QPlainTextEdit:focus {{ border-color: {theme.S500}; }}
QTableWidget {{ background: {theme.G850}; color: {theme.PAPER}; border: 1px solid {theme.G700};
    border-radius: {theme.RADIUS}px; gridline-color: {theme.G700}; selection-background-color: {theme.SOFT};
    selection-color: {theme.S600}; }}
QHeaderView::section {{ background: {theme.G900}; color: {theme.G400}; border: none;
    border-right: 1px solid {theme.G700}; border-bottom: 1px solid {theme.G700}; padding: 5px 8px;
    font-family: '{theme.MONO}'; font-size: 11px; }}
QTableCornerButton::section {{ background: {theme.G900}; border: none; }}
QComboBox {{ background: {theme.G850}; color: {theme.PAPER}; border: 1px solid {theme.G700};
    border-radius: {theme.RADIUS}px; padding: 6px 12px; min-width: 120px; }}
QComboBox QAbstractItemView {{ background: {theme.G850}; color: {theme.PAPER}; selection-background-color: {theme.SOFT};
    selection-color: {theme.S600}; }}
QFrame#card {{ background: {theme.G900}; border: 1px solid {theme.G700}; border-radius: {theme.WINDOW_RADIUS}px; }}
QLabel#chip {{ background: {theme.SOFT}; color: {theme.S600}; border-radius: 11px; padding: 3px 10px; }}
QLabel#chipWarn {{ background: {theme.TEMP_BG}; color: {theme.TEMP_FG}; border-radius: 11px; padding: 3px 10px; }}
"""


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setProperty("role", "section")
    label.setFont(theme.font(10.5, 800, caps=True))
    return label


def _value(text: str = "—", mono: bool = True, size: float = 12.5) -> QLabel:
    label = QLabel(text)
    label.setFont(theme.font(size, 500, mono=mono))
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _editor(placeholder: str) -> QPlainTextEdit:
    edit = QPlainTextEdit()
    edit.setFont(theme.font(13.5, 450, mono=True))
    edit.setPlaceholderText(placeholder)
    edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    return edit


class AnalysisWindow(QWidget):
    """Abre direto na aba que faz sentido (consulta, JSON ou tabela).

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
        self.setWindowTitle("Klick: análise")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(theme.window_stylesheet() + EXTRA_STYLE)
        self.resize(1160, 720)
        self._image = image
        self._original = ""  # texto como foi lido, para voltar depois de formatar
        self._filling = False
        self._touched = False  # o usuário já editou a consulta, o JSON ou a grade
        self._auto_tab = tab is None  # escolhe a aba pelo que foi lido
        self._candidates: list[OcrResult] = []  # leituras prontas (de cada motor)
        self._shown: OcrResult | None = None
        self._pending = 0
        self._emitted = False

        # --- topo ---
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(30, 30))
        title = QLabel("Análise")
        title.setFont(theme.font(22, 800))
        self.status = QLabel("Lendo…")
        self.status.setProperty("role", "muted")
        self.status.setFont(theme.font(12, 500, mono=True))
        self.tabs = Segmented(TABS, tab or "query")
        self.tabs.changed.connect(self._show_tab)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(logo)
        head.addWidget(title)
        head.addWidget(self.status)
        head.addStretch(1)
        head.addWidget(self.tabs)

        self.pages = QStackedWidget()
        self.inspectors = QStackedWidget()
        self._build_query()
        self._build_json()
        self._build_table()

        shot = QLabel()
        shot.setPixmap(thumbnail(image, SIDE_WIDTH - 32, 120))
        shot.setFixedSize(SIDE_WIDTH - 32, 120)
        shot.setStyleSheet(f"border: 1px solid {theme.G700}; border-radius: 8px;")
        card = QFrame(objectName="card")
        card.setFixedWidth(SIDE_WIDTH)
        side = QVBoxLayout(card)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(8)
        side.addWidget(self.inspectors, 1)
        side.addWidget(_section("Print"))
        side.addWidget(shot)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self.pages, 1)
        body.addWidget(card)

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
        layout.addLayout(body, 1)
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

    # --- montagem ----------------------------------------------------------

    def _build_query(self) -> None:
        self.query = _editor("A consulta aparece aqui assim que a leitura terminar")
        self._highlighter = sql.SqlHighlighter(self.query.document())
        self.query.textChanged.connect(self._update_query_info)
        self.query.textChanged.connect(self._on_edit)
        tidy = button("Formatar", "secondary", "sql")
        tidy.setToolTip("Consertar erros do OCR e formatar de novo")
        tidy.clicked.connect(lambda: self.query.setPlainText(sql.tidy(self.query.toPlainText())))
        original = button("Texto lido", "ghost", "undo")
        original.setToolTip("Voltar ao texto como foi lido, sem formatar")
        original.clicked.connect(lambda: self.query.setPlainText(self._original))
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(tidy)
        row.addWidget(original)
        row.addStretch(1)
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        col.addLayout(row)
        col.addWidget(self.query, 1)
        self.pages.addWidget(page)

        self.kind = _value("—", size=18)
        self.kind.setFont(theme.font(18, 700, mono=True))
        self.tables = _value()
        self.joins = _value()
        self.filters = _value()
        self.grouping = _value()
        self.ordering = _value()
        box = self._inspector([("Tipo", self.kind), ("Tabelas", self.tables), ("Junções", self.joins),
                               ("Filtros (WHERE)", self.filters), ("Agrupamento", self.grouping),
                               ("Ordem", self.ordering)])
        self.inspectors.addWidget(box)

    def _build_json(self) -> None:
        self.json_edit = _editor("O JSON aparece aqui assim que a leitura terminar")
        self._json_highlighter = sql.JsonHighlighter(self.json_edit.document())
        self.json_edit.textChanged.connect(self._on_edit)
        self.json_edit.textChanged.connect(lambda: self._json_timer.start())
        self._json_timer = QTimer(self, singleShot=True, interval=350, timeout=self._update_json_info)
        pretty = button("Formatar", "secondary", "json")
        pretty.setToolTip("Consertar aspas e vírgulas e indentar")
        pretty.clicked.connect(lambda: self._format_json(compact=False))
        compact = button("Compactar", "ghost")
        compact.setToolTip("Tudo numa linha, para colar em log ou requisição")
        compact.clicked.connect(lambda: self._format_json(compact=True))
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(pretty)
        row.addWidget(compact)
        row.addStretch(1)
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        col.addLayout(row)
        col.addWidget(self.json_edit, 1)
        self.pages.addWidget(page)

        self.json_state = QLabel("—")
        self.json_state.setFont(theme.font(12.5, 700))
        self.json_error = _value("", mono=False, size=12.5)
        self.json_counts = _value()
        self.json_fields = _value()
        state = QWidget()
        state_col = QVBoxLayout(state)
        state_col.setContentsMargins(0, 0, 0, 0)
        state_col.setSpacing(4)
        state_col.addWidget(self.json_state, 0, Qt.AlignmentFlag.AlignLeft)
        state_col.addWidget(self.json_error)
        box = self._inspector([("Situação", state), ("Tamanho", self.json_counts),
                               ("Campos do primeiro nível", self.json_fields)])
        self.inspectors.addWidget(box)

    def _build_table(self) -> None:
        self.table_name = QLineEdit(placeholderText="tabela")
        self.table_name.setAccessibleName("Nome da tabela")
        self.table_name.setFixedWidth(200)
        self.table_name.textChanged.connect(self._update_output)
        self.header = Switch(True)
        self.header.setAccessibleName("Primeira linha é o cabeçalho")
        self.header.toggled.connect(self._on_header)
        self.comma = Switch(True)
        self.comma.setAccessibleName("Vírgula decimal")
        self.comma.toggled.connect(self._update_output)
        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(QLabel("Tabela"))
        controls.addWidget(self.table_name)
        controls.addSpacing(12)
        controls.addWidget(self.header)
        controls.addWidget(QLabel("1ª linha é cabeçalho"))
        controls.addSpacing(12)
        controls.addWidget(self.comma)
        comma_label = QLabel("Vírgula decimal")
        comma_label.setToolTip("1.240,50 vira 1240.50 no SQL e conta como número")
        controls.addWidget(comma_label)
        controls.addStretch(1)
        remove = button("Apagar linhas", "ghost", "trash")
        remove.setToolTip("Apagar as linhas selecionadas da grade (Del)")
        remove.clicked.connect(self._remove_rows)
        controls.addWidget(remove)

        self.grid = QTableWidget()
        self.grid.setFont(theme.font(13, 450))
        self.grid.verticalHeader().setDefaultSectionSize(30)
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
        self._key_label = QLabel("WHERE")
        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        out_row.addWidget(QLabel("Copiar como"))
        out_row.addWidget(self.format)
        out_row.addSpacing(10)
        out_row.addWidget(self._key_label)
        out_row.addWidget(self.key)
        out_row.addStretch(1)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(theme.font(12.5, 450, mono=True))
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._out_highlighter = sql.SqlHighlighter(self.output.document())
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        col.addLayout(controls)
        col.addWidget(self.grid, 3)
        col.addLayout(out_row)
        col.addWidget(self.output, 2)
        self.pages.addWidget(page)

        self.table_size = QLabel("—")
        self.table_size.setFont(theme.font(18, 700))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary.setFont(theme.font(12.5, 500))
        copy_summary = button("Copiar resumo", "ghost", "sum")
        copy_summary.clicked.connect(lambda: self._copy_text(self.summary_text(), "Resumo copiado"))
        box = self._inspector([("Tamanho", self.table_size), ("Colunas", self.summary)], extra=copy_summary)
        self.inspectors.addWidget(box)

    @staticmethod
    def _inspector(rows: list[tuple[str, QWidget]], extra: QWidget | None = None) -> QScrollArea:
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 4, 0)
        col.setSpacing(4)
        for title, widget in rows:
            col.addWidget(_section(title))
            col.addWidget(widget)
            col.addSpacing(10)
        if extra is not None:
            col.addWidget(extra, 0, Qt.AlignmentFlag.AlignLeft)
        col.addStretch(1)
        inner.setObjectName("inspector")
        inner.setStyleSheet("QWidget#inspector { background: transparent; }")
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        return scroll

    # --- leitura -----------------------------------------------------------

    def _emit_done(self, future: Future) -> None:
        try:
            self._done.emit(future.result(), "")
        except Exception as exc:  # noqa: BLE001 - qualquer falha do OCR vira mensagem na janela
            log.warning("Leitura da análise falhou", exc_info=exc)
            self._done.emit(None, str(exc) or type(exc).__name__)

    def _on_edit(self) -> None:
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
        status = f"{len(self._shown.words)} palavras"
        rows = self.rows()
        if self.tabs.value == "table" and sql.looks_like_table(rows):
            status += f" · {len(rows)} × {len(rows[0])}"
        self.status.setText(status + (" · conferindo…" if self._pending else ""))
        if not self._pending and not self._emitted:
            self._emitted = True
            self.recognized.emit(self._shown)

    def _show(self, result: OcrResult) -> None:
        self._shown = result
        self._original = result.text
        self._filling = True
        self.query.setPlainText(sql.tidy(result.text) if sql.looks_like_sql(result.text) else result.text)
        reading = sql.read_json(result.text)
        self.json_edit.setPlainText(reading.text if not reading.error else result.text)
        self._filling = False
        self._update_json_info()
        self.set_rows(sql.table_rows(result.words))
        if self._auto_tab:
            tab = sql.analysis_tab(result)
            if tab and tab != self.tabs.value:
                self.tabs.set_value(tab)

    # --- consulta e JSON ---------------------------------------------------

    def _update_query_info(self) -> None:
        text = self.query.toPlainText()
        self.kind.setText(sql.kind(text) or "—")
        self.tables.setText("\n".join(sql.tables(text)) or "—")
        self.joins.setText("\n".join(sql.joins(text)) or "—")
        self.filters.setText("\n".join(sql.filters(text)) or "—")
        self.grouping.setText(sql.grouping(text) or "—")
        self.ordering.setText(sql.ordering(text) or "—")

    def _update_json_info(self) -> None:
        reading = sql.read_json(self.json_edit.toPlainText())
        if not self.json_edit.toPlainText().strip():
            self.json_state.setText("—")
            self.json_state.setObjectName("")
            self.json_error.setText("")
        elif reading.error:
            self.json_state.setText("Inválido")
            self.json_state.setObjectName("chipWarn")
            self.json_error.setText(f"{reading.error.capitalize()}. Corrija no texto ao lado.")
        else:
            self.json_state.setText("Válido")
            self.json_state.setObjectName("chip")
            self.json_error.setText("")
        self.json_state.style().unpolish(self.json_state)
        self.json_state.style().polish(self.json_state)
        if reading.error or reading.value is None:
            self.json_counts.setText("—")
            self.json_fields.setText("—")
            return
        self.json_counts.setText(f"{reading.keys} chaves · {reading.items} itens em listas · "
                                 f"{reading.depth} níveis")
        value = reading.value
        if isinstance(value, list):
            value = value[0] if value and isinstance(value[0], dict) else {}
        fields = [f"{k}: {type(v).__name__ if isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)[:40]}"
                  for k, v in (value.items() if isinstance(value, dict) else [])]
        self.json_fields.setText("\n".join(fields[:30]) or "—")

    def _format_json(self, compact: bool) -> None:
        reading = sql.read_json(self.json_edit.toPlainText())
        if reading.error:
            self.json_edit.setPlainText(reading.text)  # pelo menos o que dá para consertar sozinho
            self.message.setText(f"Ainda inválido: {reading.error}")
            return
        text = json.dumps(reading.value, ensure_ascii=False, separators=(",", ":")) if compact else reading.text
        self.json_edit.setPlainText(text)
        self.message.setText("")

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

    def stats(self) -> list[sql.ColumnStats]:
        return sql.column_stats(self.rows(), self.header.isChecked(), self.comma.isChecked())

    def summary_text(self) -> str:
        lines = [self.table_size.text()]
        for c in self.stats():
            line = f"{c.name} ({c.kind}): {c.filled} de {c.total} preenchidos, {c.distinct} diferentes"
            if c.sum is not None:
                line += (f"; soma {sql.brl(c.sum)}, média {sql.brl(c.mean)}, "
                         f"mín {sql.brl(c.min)}, máx {sql.brl(c.max)}")
            lines.append(line)
        return "\n".join(lines)

    def _update_summary(self) -> None:
        rows = self.rows()
        data = len([r for r in (rows[1:] if self.header.isChecked() else rows) if any(v.strip() for v in r)])
        cols = self.grid.columnCount()
        self.table_size.setText(f"{data} linha{'s' if data != 1 else ''} · {cols} coluna{'s' if cols != 1 else ''}")
        parts = []
        for c in self.stats():
            head = (f"<b>{escape(c.name)}</b> <span style='color:{theme.G400}'>{c.kind} · "
                    f"{c.filled}/{c.total} · {c.distinct} diferentes</span>")
            if c.sum is not None:
                head += (f"<br><span style='color:{theme.S600}'>Σ {sql.brl(c.sum)}</span>"
                         f" <span style='color:{theme.G400}'>· média {sql.brl(c.mean)} · "
                         f"{sql.brl(c.min)} a {sql.brl(c.max)}</span>")
            parts.append(head)
        self.summary.setText("<br><br>".join(parts) or "—")

    def _update_output(self, *_) -> None:
        update = self.format.value == "update"
        self._key_label.setVisible(update)
        self.key.setVisible(update)
        self.output.setPlainText(self.table_text())
        self._update_summary()

    # --- ações -------------------------------------------------------------

    def _show_tab(self, tab: str) -> None:
        index = [key for key, _ in TABS].index(tab)
        self.pages.setCurrentIndex(index)
        self.inspectors.setCurrentIndex(index)
        if tab == "table":
            self._update_output()

    def current_text(self) -> str:
        tab = self.tabs.value
        if tab == "query":
            return self.query.toPlainText()
        if tab == "json":
            return self.json_edit.toPlainText()
        return self.table_text()

    def _copy_text(self, text: str, message: str = "Copiado") -> None:
        if not text.strip():
            return
        copy_text(text)
        self.message.setText(message)

    def _copy(self) -> None:
        text = self.current_text()
        if not text.strip():
            return
        self._copy_text(text)
        label = self.copy.text()
        self.copy.setText("Copiado")
        QTimer.singleShot(1400, self.copy, lambda: self.copy.setText(label))

    def _save(self) -> None:
        text = self.current_text()
        if not text.strip():
            return
        tab = self.tabs.value
        ext = EXTENSIONS[tab if tab != "table" else self.format.value]
        try:
            path = store_text(text, ext)
        except OSError as exc:
            self.message.setText(f"Não deu para salvar: {exc}")
            return
        self.message.setText(f"Salvo em Leitura/{path.name}")
