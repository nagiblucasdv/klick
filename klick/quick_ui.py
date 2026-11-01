"""Painel de consultas: como o Windows + V, só que das suas consultas.

O atalho abre um painel pequeno junto de onde você está digitando (ou do mouse), já com o foco: digite
para filtrar, setas escolhem, Enter cola no programa que estava aberto e Ctrl+Enter só copia. Some ao
clicar fora ou com Esc. Duas abas (Tab troca): as consultas guardadas e as tabelas aprendidas, que
viram SELECT, INSERT ou UPDATE (setas para os lados trocam o modelo).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QStyle,
                               QStyledItemDelegate, QVBoxLayout)

from klick import focus, theme
from klick.analysis.schema import TEMPLATES, Schema
from klick.library import Library
from klick.widgets import Panel, Segmented, button

WIDTH, HEIGHT = 400, 500
ROLE = Qt.ItemDataRole.UserRole  # (tipo, valor): ("query", SavedQuery) ou ("table", nome)
STYLE = f"""
QLineEdit {{ background: rgba(255,255,255,0.07); color: {theme.ON_PENA}; border: 1px solid rgba(255,255,255,0.14);
    border-radius: {theme.RADIUS}px; padding: 7px 11px; font-size: 14px; selection-background-color: {theme.ACCENT}; }}
QLineEdit:focus {{ border-color: {theme.SIGNAL}; }}
QListWidget {{ background: transparent; border: none; outline: 0; }}
"""
TABS = [("queries", "Consultas"), ("tables", "Tabelas")]


class CardDelegate(QStyledItemDelegate):
    """Cartão do painel: o nome e as primeiras linhas, como os cartões do Windows + V."""

    def __init__(self, panel: "QuickPanel"):
        super().__init__(panel)
        self.panel = panel

    def sizeHint(self, option, index) -> QSize:
        kind, _ = index.data(ROLE)
        return QSize(WIDTH - 40, 84 if kind == "query" else 58)  # tabela: o nome e uma linha de colunas

    def paint(self, p: QPainter, option, index: QModelIndex) -> None:
        kind, value = index.data(ROLE)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(2, 3, -2, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30 if selected else 18 if hover else 10))
        p.drawRoundedRect(r, 3, 3)
        if selected:
            p.setBrush(theme.sheen(QRectF(0, 0, r.height(), 3)))
            p.drawRect(QRectF(r.left(), r.top() + 8, 3, r.height() - 16))
        inner = r.adjusted(14, 9, -12, -9)
        if kind == "query":
            title, lines = value.name, [line for line in value.text.strip().splitlines() if line.strip()]
            tag = f"{value.uses}×" if value.uses else ""
        else:
            title = value
            cols = self.panel.schema.tables.get(value, [])
            lines = [", ".join(cols) if cols else "sem colunas conhecidas"]
            tag = self.panel.template.buttons[self.panel.template.value].text() if selected else ""
        title_font = theme.font(14, 600, display=True)
        p.setFont(title_font)
        p.setPen(QColor("#ffffff" if selected else theme.ON_PENA))
        tag_w = QFontMetrics(theme.font(12, display=True)).horizontalAdvance(tag) + 8 if tag else 0
        p.drawText(QRectF(inner.left(), inner.top(), inner.width() - tag_w, 20), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(title_font).elidedText(title, Qt.TextElideMode.ElideRight, int(inner.width() - tag_w)))
        if tag:
            p.setFont(theme.font(12, display=True))
            p.setPen(QColor(theme.SIGNAL if kind == "table" else theme.ON_PENA_MUTED))
            p.drawText(QRectF(inner.left(), inner.top(), inner.width(), 20),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, tag)
        code = theme.font(11.5, mono=True)
        p.setFont(code)
        p.setPen(QColor(theme.ON_PENA_MUTED))
        metrics = QFontMetrics(code)
        for i, line in enumerate(lines[:3]):
            p.drawText(QRectF(inner.left(), inner.top() + 24 + i * 15, inner.width(), 15), Qt.AlignmentFlag.AlignVCenter,
                       metrics.elidedText(line.rstrip(), Qt.TextElideMode.ElideRight, int(inner.width())))
        p.restore()


class QuickPanel(Panel):
    chosen = Signal(str, bool)  # texto, colar (False = só copiar)
    libraryRequested = Signal()  # "Abrir a biblioteca" (Galeria > Consultas)
    cancelled = Signal()  # Esc: o foco volta para o programa de antes

    def __init__(self, library: Library, schema: Schema, tables: bool = True):
        super().__init__()
        self.library, self.schema = library, schema
        self.setStyleSheet(theme.panel_stylesheet() + STYLE)
        self.setFixedSize(WIDTH, HEIGHT)
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 12, 12, 10)
        col.setSpacing(8)

        self.tabs = Segmented(TABS if tables else TABS[:1], "queries")
        self.tabs.changed.connect(lambda _: self.refresh())
        col.addWidget(self.tabs)
        self.search = QLineEdit(placeholderText="Digite para filtrar")
        self.search.setAccessibleName("Filtrar")
        self.search.textChanged.connect(lambda _: self.refresh())
        self.search.installEventFilter(self)
        col.addWidget(self.search)
        self.template = Segmented(TEMPLATES, "select")
        self.template.changed.connect(lambda _: self.list.viewport().update())
        col.addWidget(self.template)

        self.list = QListWidget()
        self.list.setItemDelegate(CardDelegate(self))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # o foco fica na busca: digitar sempre filtra
        self.list.itemClicked.connect(lambda _: self.accept(paste=True))
        col.addWidget(self.list, 1)
        self.empty = QLabel(wordWrap=True, alignment=Qt.AlignmentFlag.AlignCenter)
        self.empty.setProperty("role", "muted")
        col.addWidget(self.empty, 1)

        foot = QHBoxLayout()
        hint = QLabel("Enter cola, Ctrl+Enter só copia, Esc fecha")
        hint.setProperty("role", "muted")
        hint.setFont(theme.font(12))
        library_button = button("Biblioteca", "ghost", "sql", on_pena=True)
        library_button.setToolTip("Abrir Galeria > Consultas, para criar, editar ou importar")
        library_button.clicked.connect(self._open_library)
        foot.addWidget(hint, 1)
        foot.addWidget(library_button)
        col.addLayout(foot)
        self._closing = False
        self.refresh()

    # --- mostrar ----------------------------------------------------------------------------

    def show_at(self, pos: QPoint) -> None:
        """Abre logo abaixo de `pos` (o cursor de texto ou o mouse), sem sair da tela, já com o foco."""
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(pos.x() - 24, area.left() + 8), area.right() - self.width() - 8)
        y = pos.y() + 8
        if y + self.height() > area.bottom() - 8:
            y = pos.y() - self.height() - 28  # sem espaço embaixo: abre em cima da linha
        y = min(max(y, area.top() + 8), area.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()
        focus.take(self)
        self.search.setFocus()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate and self.isVisible() and not self._closing:
            self.close()  # clicou fora: some, como o Windows + V
        return super().event(event)

    # --- lista -------------------------------------------------------------------------------

    def refresh(self) -> None:
        text = self.search.text()
        tables = self.tabs.value == "tables"
        self.template.setVisible(tables)
        self.list.clear()
        if tables:
            items = [("table", name) for name in self.schema.search(text)]
        else:
            items = [("query", q) for q in self.library.search(text)]
        for item in items:
            row = QListWidgetItem()
            row.setData(ROLE, item)
            self.list.addItem(row)
        if items:
            self.list.setCurrentRow(0)
        self.list.setVisible(bool(items))
        self.empty.setVisible(not items)
        if text:
            self.empty.setText(f"Nada com “{text}”.")
        elif tables:
            self.empty.setText("Ainda não conheço nenhuma tabela.\n\nCom “Aprender tabelas e colunas” ligado nas "
                               "configurações, cada consulta que você copia na Análise ensina as tabelas dela.")
        else:
            self.empty.setText("Nenhuma consulta guardada ainda.\n\nNa Análise (Ctrl+Q na captura), use Guardar "
                               "consulta; ou crie na Biblioteca.")

    def current_text(self) -> str:
        item = self.list.currentItem()
        if item is None:
            return ""
        kind, value = item.data(ROLE)
        return value.text if kind == "query" else self.schema.template(value, self.template.value)

    # --- escolher ---------------------------------------------------------------------------

    def accept(self, paste: bool = True) -> None:
        item = self.list.currentItem()
        text = self.current_text()
        if item is None or not text.strip():
            return
        kind, value = item.data(ROLE)
        if kind == "query":
            self.library.used(value.id)
        self._closing = True
        self.close()
        self.chosen.emit(text, paste)

    def _open_library(self) -> None:
        self._closing = True
        self.close()
        self.libraryRequested.emit()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            key, mods = event.key(), event.modifiers()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow() + (1 if key == Qt.Key.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(row, self.list.count() - 1)))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.accept(paste=not mods & Qt.KeyboardModifier.ControlModifier)
                return True
            if key == Qt.Key.Key_Escape:
                self._closing = True
                self.close()
                self.cancelled.emit()
                return True
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and len(self.tabs.buttons) > 1:
                self.tabs.set_value("tables" if self.tabs.value == "queries" else "queries")
                return True
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.tabs.value == "tables" and not self.search.text():
                keys = [k for k, _ in TEMPLATES]
                step = 1 if key == Qt.Key.Key_Right else -1
                self.template.set_value(keys[(keys.index(self.template.value) + step) % len(keys)])
                return True
        return super().eventFilter(obj, event)
