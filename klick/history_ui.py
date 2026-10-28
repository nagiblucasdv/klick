"""Janela do histórico: busca pelo texto das capturas e miniaturas."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QStackedLayout, QVBoxLayout, QWidget)

from klick.actions import copy_image, copy_text
from klick.history import Entry, History
from klick.icon import app_icon

THUMB = QSize(200, 112)
SOURCES = {"copy": "Copiado", "save": "Salvo", "ocr": "OCR", "edit": "Editado"}

STYLE = """
QWidget#history { background: #111827; color: #f9fafb; }
QLabel { color: #d1d5db; }
QLineEdit { background: #1f2937; color: #f9fafb; border: 1px solid #374151; border-radius: 6px; padding: 7px 10px; }
QLineEdit:focus { border-color: #3b82f6; }
QListWidget { background: #111827; border: none; color: #d1d5db; }
QListWidget::item { border-radius: 6px; padding: 6px; }
QListWidget::item:selected, QListWidget::item:hover { background: #1f2937; color: #f9fafb; }
QLabel#empty { color: #9ca3af; }
QLabel#status { color: #9ca3af; }
"""


class HistoryWindow(QWidget):
    def __init__(self, history: History):
        super().__init__(None, Qt.WindowType.Window)
        self._history = history
        self.setObjectName("history")
        self.setWindowTitle("Klick: histórico")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE)
        self.resize(980, 640)

        label = QLabel("Buscar")
        self._search = QLineEdit(placeholderText='Texto que aparecia no print, ex.: erro 500')
        self._search.setClearButtonEnabled(True)
        label.setBuddy(self._search)
        self._debounce = QTimer(self, singleShot=True, interval=200, timeout=self.refresh)
        self._search.textChanged.connect(self._debounce.start)

        self._list = QListWidget()
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setIconSize(THUMB)
        self._list.setGridSize(QSize(THUMB.width() + 20, THUMB.height() + 40))
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setUniformItemSizes(True)
        self._list.setWordWrap(True)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)
        self._list.itemActivated.connect(lambda item: self._copy_image(item.data(Qt.ItemDataRole.UserRole)))

        self._empty = QLabel(objectName="empty", alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self._status = QLabel(objectName="status")

        stack = QStackedLayout()
        stack.addWidget(self._list)
        stack.addWidget(self._empty)
        self._stack = stack

        top = QHBoxLayout()
        top.addWidget(label)
        top.addWidget(self._search, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addLayout(stack, 1)
        layout.addWidget(self._status)

        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._search.setFocus)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        QShortcut(QKeySequence.StandardKey.Copy, self, activated=self._copy_selected)
        QShortcut(QKeySequence.StandardKey.Delete, self, activated=self._delete_selected)

        history.changed.connect(self._on_changed)
        self.refresh()

    def refresh(self) -> None:
        query = self._search.text().strip()
        entries = self._history.search(query)
        self._list.clear()
        for entry in entries:
            item = QListWidgetItem(QIcon(QPixmap(str(entry.thumb_path))), self._caption(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            snippet = " ".join(entry.text.split())[:240]
            item.setToolTip(snippet or "Sem texto reconhecido")
            self._list.addItem(item)

        if entries:
            self._stack.setCurrentWidget(self._list)
        elif query:
            self._empty.setText(f'Nada encontrado para "{query}".\nA busca usa o texto que o OCR leu em cada captura.')
            self._stack.setCurrentWidget(self._empty)
        elif not self._history.enabled:
            self._empty.setText("O histórico está desligado.\nLigue em \"Guardar histórico\" no menu da bandeja.")
            self._stack.setCurrentWidget(self._empty)
        else:
            self._empty.setText("Nenhuma captura ainda.\nAperte PrintScreen, selecione uma área e copie ou salve.")
            self._stack.setCurrentWidget(self._empty)
        count = len(entries)
        self._status.setText(f"{count} captura{'s' if count != 1 else ''}  ·  Enter ou duplo clique copia a imagem"
                             if count else "")

    @staticmethod
    def _caption(entry: Entry) -> str:
        return f"{entry.created_at:%d/%m %H:%M}  ·  {SOURCES.get(entry.source, entry.source)}"

    def _on_changed(self) -> None:
        if self.isVisible():
            self._debounce.start()

    def _selected_id(self) -> int | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _copy_selected(self) -> None:
        if (entry_id := self._selected_id()) is not None:
            self._copy_image(entry_id)

    def _delete_selected(self) -> None:
        if (entry_id := self._selected_id()) is not None:
            self._delete(entry_id)

    def _copy_image(self, entry_id: int) -> None:
        entry = self._history.get(entry_id)
        if entry:
            copy_image(QImage(str(entry.image_path)))
            self._status.setText("Imagem copiada para a área de transferência")

    def _copy_text(self, entry_id: int) -> None:
        entry = self._history.get(entry_id)
        if entry and entry.text:
            copy_text(entry.text)
            self._status.setText("Texto copiado para a área de transferência")

    def _delete(self, entry_id: int) -> None:
        answer = QMessageBox.question(self, "Excluir captura", "Excluir esta captura do histórico?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes:
            self._history.delete(entry_id)

    def _context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        entry = self._history.get(item.data(Qt.ItemDataRole.UserRole))
        if entry is None:
            return
        menu = QMenu(self)
        menu.addAction("Copiar imagem", lambda: self._copy_image(entry.id))
        copy_txt = menu.addAction("Copiar texto", lambda: self._copy_text(entry.id))
        copy_txt.setEnabled(bool(entry.text))
        menu.addAction("Abrir imagem", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.image_path))))
        menu.addSeparator()
        menu.addAction("Excluir captura…", lambda: self._delete(entry.id))
        menu.exec(self._list.viewport().mapToGlobal(pos))
