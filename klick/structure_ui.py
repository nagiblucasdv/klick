"""Autocompletar de estrutura: pelo atalho, as tabelas que o Klick aprendeu, com o SELECT, o INSERT ou o
UPDATE prontos para copiar.

Abre perto do mouse. Digite parte do nome da tabela, escolha o modelo (Tab troca) e Enter copia.
Só copia: você cola onde quiser.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QVBoxLayout

from klick import theme
from klick.actions import copy_text
from klick.analysis.schema import TEMPLATES, Schema
from klick.widgets import Panel, Segmented, button

STYLE = f"""
QLineEdit {{ background: rgba(255,255,255,0.07); color: {theme.ON_PENA}; border: 1px solid rgba(255,255,255,0.14);
    border-radius: {theme.RADIUS}px; padding: 8px 12px; font-size: 15px; selection-background-color: {theme.ACCENT}; }}
QLineEdit:focus {{ border-color: {theme.SIGNAL}; }}
QListWidget {{ background: transparent; border: none; outline: 0; color: {theme.ON_PENA}; }}
QListWidget::item {{ padding: 7px 10px; border-radius: 3px; border-left: 2px solid transparent; }}
QListWidget::item:selected {{ background: rgba(255,255,255,0.10); color: #ffffff; border-left: 2px solid {theme.SIGNAL}; }}
QPlainTextEdit {{ background: rgba(0,0,0,0.25); color: {theme.ON_PENA}; border: 1px solid rgba(255,255,255,0.08);
    border-radius: {theme.RADIUS}px; padding: 8px; }}
"""


class StructurePicker(Panel):
    copied = Signal(str, str)  # tabela, modelo ("SELECT"…)

    def __init__(self, schema: Schema):
        super().__init__()
        self.schema = schema
        self.setStyleSheet(theme.panel_stylesheet() + STYLE)
        self.setFixedSize(620, 400)
        col = QVBoxLayout(self)
        col.setContentsMargins(16, 16, 16, 14)
        col.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("Estrutura")
        title.setFont(theme.font(19, 600, display=True))
        self.count = QLabel()
        self.count.setProperty("role", "muted")
        self.template = Segmented(TEMPLATES, "select")
        self.template.changed.connect(lambda _: self._preview())
        head.addWidget(title)
        head.addWidget(self.count, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        head.addWidget(self.template)
        col.addLayout(head)

        self.search = QLineEdit(placeholderText="Nome da tabela")
        self.search.setAccessibleName("Buscar tabela")
        self.search.textChanged.connect(self.refresh)
        self.search.installEventFilter(self)
        col.addWidget(self.search)

        body = QHBoxLayout()
        body.setSpacing(10)
        self.tables = QListWidget()
        self.tables.setFixedWidth(200)
        self.tables.setFont(theme.font(13.5))
        self.tables.currentRowChanged.connect(lambda _: self._preview())
        self.tables.itemActivated.connect(lambda _: self.accept())
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(theme.font(12.5, mono=True))
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        body.addWidget(self.tables)
        body.addWidget(self.preview, 1)
        col.addLayout(body, 1)

        foot = QHBoxLayout()
        hint = QLabel("Enter copia, Tab troca o modelo, Esc fecha")
        hint.setProperty("role", "muted")
        self.forget = button("Esquecer tabela", "ghost", "trash", on_pena=True)
        self.forget.setToolTip("Tira esta tabela da lista (ela volta se aparecer numa consulta de novo)")
        self.forget.clicked.connect(self._forget)
        copy = button("Copiar", "primary", "copy")
        copy.clicked.connect(self.accept)
        foot.addWidget(hint, 1)
        foot.addWidget(self.forget)
        foot.addWidget(copy)
        col.addLayout(foot)

        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        self.refresh()

    def show_near(self, pos: QPoint | None = None) -> None:
        """Abre perto do mouse, sem sair da tela, e já pronto para digitar."""
        pos = pos or QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(pos.x() - 40, area.left() + 8), area.right() - self.width() - 8)
        y = min(max(pos.y() + 18, area.top() + 8), area.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    def refresh(self) -> None:
        names = self.schema.search(self.search.text())
        self.tables.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setToolTip(", ".join(self.schema.tables.get(name, [])))
            self.tables.addItem(item)
        total = len(self.schema.tables)
        self.count.setText(f"{total} tabela{'s' if total != 1 else ''}")
        if names:
            self.tables.setCurrentRow(0)
        self._preview()

    def current_table(self) -> str | None:
        item = self.tables.currentItem()
        return item.text() if item else None

    def _preview(self) -> None:
        table = self.current_table()
        self.forget.setEnabled(table is not None)
        if table is not None:
            self.preview.setPlainText(self.schema.template(table, self.template.value))
        elif self.schema.tables:
            self.preview.setPlainText(f"Nenhuma tabela com “{self.search.text()}”.")
        else:
            self.preview.setPlainText(
                "Ainda não conheço nenhuma tabela.\n\nCopie consultas na Análise (Ctrl+Q na captura): cada uma ensina "
                "as tabelas e as colunas que cita.")

    def accept(self) -> None:
        table = self.current_table()
        if table is None:
            return
        kind = self.template.value
        copy_text(self.schema.template(table, kind))
        self.copied.emit(table, dict(TEMPLATES)[kind])
        self.close()

    def _forget(self) -> None:
        table = self.current_table()
        if table is not None:
            self.schema.forget(table)
            self.refresh()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.search and event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.tables.currentRow() + (1 if key == Qt.Key.Key_Down else -1)
                self.tables.setCurrentRow(max(0, min(row, self.tables.count() - 1)))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.accept()
                return True
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                keys = [k for k, _ in TEMPLATES]
                step = -1 if key == Qt.Key.Key_Backtab else 1
                self.template.set_value(keys[(keys.index(self.template.value) + step) % len(keys)])
                return True
        return super().eventFilter(obj, event)
