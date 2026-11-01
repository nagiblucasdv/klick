"""Página Consultas da galeria: todas as consultas guardadas numa página só.

À esquerda, a lista (nome, tabelas, quantas vezes foi usada; as mais usadas em cima); à direita, a
consulta escolhida, editável, com as cores do SQL. O que você muda é guardado sozinho, um instante
depois de parar de digitar. A busca do topo da galeria procura no nome e no texto.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path

from PySide6.QtCore import QModelIndex, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QStackedWidget,
                               QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from klick import config, theme
from klick.actions import copy_text
from klick.analysis import query
from klick.analysis_ui import CodeEdit
from klick.library import Library, SavedQuery
from klick.widgets import button, confirm, icon_button

ROLE = Qt.ItemDataRole.UserRole
ROW_HEIGHT = 70
SAVE_AFTER_MS = 600


class QueryDelegate(QStyledItemDelegate):
    """Linha da lista: nome, tabelas e usos, e o começo da consulta em fonte de código."""

    def sizeHint(self, option, index) -> QSize:
        return QSize(260, ROW_HEIGHT)

    def paint(self, p: QPainter, option, index: QModelIndex) -> None:
        item: SavedQuery = index.data(ROLE)
        if item is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(0, 1, 0, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.ACCENT_SOFT if selected else theme.SUNKEN))
            p.drawRoundedRect(r, 3, 3)
        if selected:
            bar = QRectF(r.left(), r.top() + 8, 3, r.height() - 16)
            p.fillRect(bar, theme.sheen(QRectF(0, bar.top(), r.height(), bar.height())))
        text = r.adjusted(14, 8, -12, -8)
        name_font = theme.font(13.5, 600)
        meta_font = theme.font(12)
        p.setFont(name_font)
        p.setPen(QColor(theme.ACCENT_TEXT if selected else theme.INK))
        p.drawText(QRectF(text.left(), text.top(), text.width(), 20), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(name_font).elidedText(item.name, Qt.TextElideMode.ElideRight, int(text.width())))
        uses = f"usada {item.uses}×" if item.uses else "nunca usada"
        p.setFont(meta_font)
        metrics = QFontMetrics(meta_font)
        uses_w = metrics.horizontalAdvance(uses) + 4
        line = QRectF(text.left(), text.top() + 20, text.width(), 18)
        p.setPen(QColor(theme.MUTED))
        p.drawText(line.adjusted(0, 0, -uses_w - 8, 0), Qt.AlignmentFlag.AlignVCenter,
                   metrics.elidedText(", ".join(item.tables) or "sem tabela", Qt.TextElideMode.ElideRight,
                                      int(line.width() - uses_w - 8)))
        p.setPen(QColor(theme.FAINT))
        p.drawText(line, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, uses)
        code_font = theme.font(11.5, mono=True)
        p.setFont(code_font)
        first = " ".join(item.text.split())
        p.drawText(QRectF(text.left(), text.top() + 38, text.width(), 16), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(code_font).elidedText(first, Qt.TextElideMode.ElideRight, int(text.width())))
        p.restore()


class LibraryPage(QWidget):
    message = Signal(str)  # o que aconteceu, para a linha de status da galeria

    def __init__(self, library: Library):
        super().__init__()
        self.library = library
        self._current: int | None = None
        self._filling = False
        self._search = ""
        library.changed.connect(self._on_changed)
        self._saving = False

        # --- lista ---
        new = button("Nova consulta", "secondary", "plus")
        new.clicked.connect(self.new_query)
        imp = icon_button("folder", "Importar .sql: cada arquivo vira uma consulta com o nome dele")
        imp.clicked.connect(self._import)
        exp = icon_button("save", "Exportar tudo num .sql só, cada consulta com o nome em comentário (backup)")
        exp.clicked.connect(self._export)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        tools.addWidget(new)
        tools.addStretch(1)
        tools.addWidget(imp)
        tools.addWidget(exp)
        self.list = QListWidget()
        self.list.setItemDelegate(QueryDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setFrameShape(QListWidget.Shape.NoFrame)
        self.list.setStyleSheet(f"QListWidget {{ background: {theme.SURFACE}; border: 1px solid {theme.LINE};"
                                f" border-radius: {theme.RADIUS}px; padding: 4px; outline: 0; }}")
        self.list.currentItemChanged.connect(lambda item, _: self._show(item.data(ROLE).id if item else None))
        self.list.itemDoubleClicked.connect(lambda _: self.copy())
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addLayout(tools)
        left.addWidget(self.list, 1)

        # --- a consulta escolhida ---
        self.name = QLineEdit(objectName="queryName")
        self.name.setAccessibleName("Nome da consulta")
        self.name.setFont(theme.font(19, 600, display=True))
        self.name.textEdited.connect(lambda _: self._autosave.start())
        self.meta = QLabel()
        self.meta.setProperty("role", "muted")
        self.editor = CodeEdit("sql")
        self.editor.textChanged.connect(self._on_text)
        tidy = button("Formatar", "secondary", "sql")
        tidy.setToolTip("Uma cláusula por linha, palavras-chave em maiúsculas")
        tidy.clicked.connect(self._format)
        duplicate = button("Duplicar", "ghost", "copy")
        duplicate.clicked.connect(self._duplicate)
        delete = button("Excluir", "ghost", "trash")
        delete.clicked.connect(self.delete_current)
        self.copy_button = button("Copiar", "primary", "copy")
        self.copy_button.setToolTip(theme.tip("Copiar a consulta", "Ctrl C"))
        self.copy_button.clicked.connect(self.copy)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(tidy)
        actions.addWidget(duplicate)
        actions.addWidget(delete)
        actions.addStretch(1)
        actions.addWidget(self.copy_button)
        detail = QWidget()
        right = QVBoxLayout(detail)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        right.addWidget(self.name)
        right.addWidget(self.meta)
        right.addWidget(self.editor, 1)
        right.addLayout(actions)

        # --- vazio ---
        self._empty = QWidget()
        empty = QVBoxLayout(self._empty)
        empty.addStretch(1)
        self._empty_title = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._empty_title.setFont(theme.font(20, 600, display=True))
        self._empty_text = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self._empty_text.setProperty("role", "muted")
        empty.addWidget(self._empty_title)
        empty.addWidget(self._empty_text)
        empty.addStretch(2)
        self._right = QStackedWidget()
        self._right.addWidget(detail)
        self._right.addWidget(self._empty)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        left_box = QWidget()
        left_box.setLayout(left)
        left.setContentsMargins(0, 0, 0, 0)
        left_box.setFixedWidth(330)
        row.addWidget(left_box)
        row.addWidget(self._right, 1)

        self._autosave = QTimer(self, singleShot=True, interval=SAVE_AFTER_MS, timeout=self._save)

    # --- lista ----------------------------------------------------------------------------

    def refresh(self, search: str | None = None) -> None:
        """Monta a lista de novo (com a busca), sem perder a consulta escolhida nem o que está sendo digitado."""
        if search is not None:
            self._search = search
        self._save()  # o que estava pendente vai antes de recarregar
        items = self.library.search(self._search)
        keep = self._current
        self.list.blockSignals(True)
        self.list.clear()
        for item in items:
            row = QListWidgetItem()
            row.setData(ROLE, item)
            row.setToolTip(item.text[:400])
            self.list.addItem(row)
        self.list.blockSignals(False)
        ids = [item.id for item in items]
        if keep in ids:
            self.list.setCurrentRow(ids.index(keep))
            self._show(keep, reload=False)
        elif ids:
            self.list.setCurrentRow(0)
            self._show(ids[0])
        else:
            self._show(None)

    def select(self, query_id: int) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(ROLE).id == query_id:
                self.list.setCurrentRow(i)
                return

    def _show(self, query_id: int | None, reload: bool = True) -> None:
        if query_id != self._current:
            self._save()
        self._current = query_id
        item = self.library.get(query_id) if query_id is not None else None
        if item is None:
            if self._search:
                self._empty_title.setText(f"Nenhuma consulta com “{self._search}”")
                self._empty_text.setText("A busca procura no nome e no texto de cada consulta.")
            else:
                self._empty_title.setText("Nenhuma consulta guardada ainda")
                self._empty_text.setText("Na Análise (Ctrl+Q na captura), use Guardar consulta. Ou crie aqui com Nova "
                                         "consulta, ou traga os seus arquivos com Importar .sql.")
            self._right.setCurrentWidget(self._empty)
            return
        self._right.setCurrentWidget(self._right.widget(0))
        if reload:
            with self._quiet():
                self.name.setText(item.name)
                self.editor.setPlainText(item.text)
        self._update_meta(item)

    def _update_meta(self, item: SavedQuery) -> None:
        kind = query.parse(item.text).kind or "SQL"
        parts = [f"{kind} em {', '.join(item.tables)}" if item.tables else kind,
                 f"Guardada em {item.created_at:%d/%m/%Y}"]
        if item.used_at:
            parts.append(f"Copiada pela última vez em {item.used_at:%d/%m às %H:%M}")
        self.meta.setText(". ".join(parts) + ".")

    @contextmanager
    def _quiet(self):
        was, self._filling = self._filling, True
        try:
            yield
        finally:
            self._filling = was

    # --- edição -------------------------------------------------------------------------------

    def _on_text(self) -> None:
        if not self._filling:
            self._autosave.start()

    def _save(self) -> None:
        if not self._autosave.isActive() or self._current is None:
            return
        self._autosave.stop()
        self._saving = True
        try:
            self.library.update(self._current, name=self.name.text(), text=self.editor.toPlainText())
        finally:
            self._saving = False
        item = self.library.get(self._current)
        if item is not None:
            current = self.list.currentItem()
            if current is not None and current.data(ROLE).id == item.id:
                current.setData(ROLE, item)
            self._update_meta(item)
        self.message.emit("Guardado")

    def _on_changed(self) -> None:
        if not self._saving and self.isVisible():
            self.refresh()

    def _format(self) -> None:
        text = query.format_sql(self.editor.toPlainText())
        if text.strip():
            self.editor.setPlainText(text)

    # --- ações --------------------------------------------------------------------------------

    def copy(self) -> None:
        if self._current is None or not self.editor.toPlainText().strip():
            return
        self._save()
        copy_text(self.editor.toPlainText())
        self._saving = True
        try:
            self.library.used(self._current)
        finally:
            self._saving = False
        name = self.name.text()
        self.refresh()
        self.message.emit(f"“{name}” copiada")

    def new_query(self) -> None:
        self._save()
        query_id = self.library.add("Nova consulta", "SELECT *\nFROM \nWHERE ")
        self.refresh("")
        self.select(query_id)
        self.name.setFocus()
        self.name.selectAll()

    def _duplicate(self) -> None:
        if self._current is None:
            return
        self._save()
        query_id = self.library.add(f"{self.name.text()} (cópia)", self.editor.toPlainText())
        self.refresh()
        self.select(query_id)

    def delete_current(self) -> None:
        if self._current is None:
            return
        if confirm(self, "Excluir esta consulta?", f"“{self.name.text()}” sai da biblioteca de vez.", "Excluir consulta"):
            self._autosave.stop()
            self.library.delete(self._current)
            self._current = None
            self.refresh()
            self.message.emit("Consulta excluída")

    def _import(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Importar consultas", str(config.folder("reading")),
                                                "SQL (*.sql);;Texto (*.txt);;Todos (*.*)")
        if not paths:
            return
        added = self.library.import_files([Path(p) for p in paths])
        skipped = len(paths) - added
        self.refresh("")
        text = f"{added} consulta{'s' if added != 1 else ''} importada{'s' if added != 1 else ''}"
        self.message.emit(text + (f"; {skipped} já estava{'m' if skipped != 1 else ''} na biblioteca" if skipped else ""))

    def _export(self) -> None:
        if not self.library.count():
            self.message.emit("Nada para exportar ainda")
            return
        self._save()
        folder = config.folder("reading")
        folder.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Exportar consultas",
                                              str(folder / f"consultas_{date.today():%Y-%m-%d}.sql"), "SQL (*.sql)")
        if not path:
            return
        try:
            Path(path).write_text(self.library.export(), encoding="utf-8")
        except OSError as exc:
            self.message.emit(f"Não deu para exportar: {exc}")
            return
        self.message.emit(f"{self.library.count()} consultas exportadas para {Path(path).name}")
