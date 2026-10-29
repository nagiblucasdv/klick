"""Galeria: as capturas em quatro coleções (prints, gravações, GIFs e leitura), com busca no texto."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QModelIndex, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QFontMetrics, QImage, QKeySequence, QPainter,
                           QPainterPath, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMenu, QStackedLayout, QStyle, QStyledItemDelegate, QToolButton,
                               QVBoxLayout, QWidget)

from klick import icons, theme
from klick.actions import copy_file, copy_image, copy_text
from klick.history import Collection, Entry, History
from klick.icon import app_icon
from klick.widgets import ShutterButton, button, confirm

CARD = QSize(204, 128)  # miniatura
CAPTION = 40
GAP = 14

COLLECTIONS = [
    (Collection.PRINTS, "image", "Prints"),
    (Collection.RECORDINGS, "video", "Gravações"),
    (Collection.GIFS, "gif", "GIFs"),
    (Collection.READING, "read", "Leitura"),
]
EMPTY = {
    Collection.PRINTS: ("Nenhum print ainda", "Aperte PrintScreen, selecione uma área e copie ou salve."),
    Collection.RECORDINGS: ("Nenhuma gravação ainda", "Na seleção, escolha Gravar ou aperte Ctrl+Shift+R."),
    Collection.GIFS: ("Nenhum GIF ainda", "Na seleção, escolha GIF para gravar um GIF curto."),
    Collection.READING: ("Nada lido ainda", "Escolha Ler na seleção ou aperte Ctrl+Shift+T sobre um texto."),
}
NOUNS = {Collection.PRINTS: ("print", "prints"), Collection.RECORDINGS: ("gravação", "gravações"),
         Collection.GIFS: ("GIF", "GIFs"), Collection.READING: ("leitura", "leituras")}
ENTRY_ROLE = Qt.ItemDataRole.UserRole


def when(entry: Entry) -> str:
    day = entry.created_at.date()
    if day == date.today():
        return entry.created_at.strftime("%H:%M")
    if day == date.today() - timedelta(days=1):
        return "ontem"
    return entry.created_at.strftime("%d/%m")


def title(entry: Entry) -> str:
    if entry.kind in ("video", "gif") and entry.media:
        return entry.media.stem
    words = " ".join(entry.text.split())
    return words[:60] if words else f"Print {entry.width} × {entry.height}"


def duration(seconds: float | None) -> str:
    if not seconds:
        return ""
    s = round(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


class CardDelegate(QStyledItemDelegate):
    """Miniatura com o anel laranja quando selecionada, título, hora e selo de duração."""

    def __init__(self, scheme: theme.Scheme, parent=None):
        super().__init__(parent)
        self._s = scheme
        self._title_font = theme.font(12.5, 500)
        self._meta_font = theme.font(11, 400, mono=True)
        self._badge_font = theme.font(10.5, 600, mono=True)
        self._cache: dict[int, QPixmap] = {}

    def sizeHint(self, option, index) -> QSize:
        return QSize(CARD.width() + GAP, CARD.height() + CAPTION + GAP)

    def forget(self) -> None:
        self._cache.clear()

    def _thumb(self, entry: Entry, ratio: float) -> QPixmap:
        pm = self._cache.get(entry.id)
        if pm is None:
            image = QImage(str(entry.thumb_path))
            pm = QPixmap(round(CARD.width() * ratio), round(CARD.height() * ratio))
            pm.fill(QColor(theme.A200 if not self._s.dark else theme.G800))
            if not image.isNull():
                scaled = image.scaled(pm.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation)
                p = QPainter(pm)
                p.drawImage(0, 0, scaled, 0, 0, pm.width(), pm.height())  # canto de cima à esquerda: onde fica o contexto
                p.end()
            pm.setDevicePixelRatio(ratio)
            self._cache[entry.id] = pm
        return pm

    def paint(self, p: QPainter, option, index: QModelIndex) -> None:
        entry: Entry = index.data(ENTRY_ROLE)
        if entry is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cell = option.rect
        card = QRectF(cell.left() + GAP / 2, cell.top() + GAP / 2, CARD.width(), CARD.height())
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        clip = QPainterPath()
        clip.addRoundedRect(card, 3, 3)
        p.setClipPath(clip)
        p.drawPixmap(card.toRect(), self._thumb(entry, p.device().devicePixelRatioF()))
        p.setClipping(False)
        ring = QPen(QColor(theme.S500), 3) if selected else QPen(QColor(self._s.muted if hover else self._s.line), 1)
        p.setPen(ring)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(card.adjusted(-1, -1, 1, 1) if selected else card, 3, 3)

        badge = {"video": duration(entry.duration) or "MP4", "gif": "GIF"}.get(entry.kind)
        if badge:
            p.setFont(self._badge_font)
            w = QFontMetrics(self._badge_font).horizontalAdvance(badge) + 12
            box = QRectF(card.right() - w - 6, card.bottom() - 24, w, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(18, 17, 16, 215))
            p.drawRoundedRect(box, 2, 2)
            p.setPen(QColor("#ffffff"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, badge)

        meta = when(entry)
        p.setFont(self._meta_font)
        meta_w = QFontMetrics(self._meta_font).horizontalAdvance(meta)
        line = QRectF(card.left(), card.bottom() + 8, card.width(), 18)
        p.setPen(QColor(self._s.muted))
        p.drawText(line, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, meta)
        p.setFont(self._title_font)
        text = QFontMetrics(self._title_font).elidedText(title(entry), Qt.TextElideMode.ElideRight,
                                                        int(card.width() - meta_w - 10))
        p.setPen(QColor(self._s.fg))
        p.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        p.restore()


class HistoryWindow(QWidget):
    captureRequested = Signal()
    readRequested = Signal(QImage)
    markRequested = Signal(QImage)

    def __init__(self, history: History):
        super().__init__(None, Qt.WindowType.Window)
        self._history = history
        self._scheme = theme.window_scheme()
        self.setObjectName("window")
        self.setWindowTitle("Klick: galeria")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(theme.window_stylesheet(self._scheme))
        self.resize(1000, 680)
        self.collection = Collection.PRINTS

        shutter = ShutterButton(30)
        shutter.setToolTip(theme.tip("Nova captura", "PrtSc"))
        shutter.setAccessibleName("Nova captura")
        shutter.clicked.connect(self.captureRequested.emit)
        heading = QLabel("Galeria")
        heading.setFont(theme.font(22, 800, 125))
        self._search = QLineEdit(placeholderText="Buscar no texto dos prints, ex.: erro 500")
        self._search.setClearButtonEnabled(True)
        self._search.addAction(icons.icon("search", self._scheme.muted, size=16),
                               QLineEdit.ActionPosition.LeadingPosition)
        self._search.setMinimumWidth(320)
        self._search.setAccessibleName("Buscar")
        self._debounce = QTimer(self, singleShot=True, interval=200, timeout=self.refresh)
        self._search.textChanged.connect(self._debounce.start)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(shutter)
        top.addWidget(heading)
        top.addStretch(1)
        top.addWidget(self._search)

        dial = QFrame(objectName="dial")
        dial_row = QHBoxLayout(dial)
        dial_row.setContentsMargins(3, 3, 3, 3)
        dial_row.setSpacing(2)
        self._tabs = QButtonGroup(self)
        self._tab_buttons: dict[Collection, QToolButton] = {}
        for collection, icon_name, label in COLLECTIONS:
            tab = QToolButton()
            tab.setCheckable(True)
            tab.setChecked(collection is self.collection)
            tab.setIcon(icons.icon(icon_name, self._scheme.muted, hover=self._scheme.fg, checked=theme.S500, size=16))
            tab.setIconSize(QSize(16, 16))
            tab.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.setProperty("label", label)
            tab.clicked.connect(lambda _=False, c=collection: self.show_collection(c))
            self._tabs.addButton(tab)
            self._tab_buttons[collection] = tab
            dial_row.addWidget(tab)
        dial_line = QHBoxLayout()
        dial_line.addWidget(dial)
        dial_line.addStretch(1)

        self._delegate = CardDelegate(self._scheme, self)
        self._list = QListWidget()
        self._list.setViewMode(QListView.ViewMode.IconMode)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setMovement(QListView.Movement.Static)
        self._list.setUniformItemSizes(True)
        self._list.setGridSize(self._delegate.sizeHint(None, None))
        self._list.setItemDelegate(self._delegate)
        self._list.setMouseTracking(True)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)
        self._list.itemActivated.connect(lambda item: self._activate(item.data(ENTRY_ROLE)))
        self._list.currentItemChanged.connect(lambda *_: self._update_status())

        self._empty = QWidget()
        empty_col = QVBoxLayout(self._empty)
        empty_col.addStretch(1)
        self._empty_title = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._empty_title.setFont(theme.font(17, 750, 112))
        self._empty_text = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self._empty_text.setProperty("role", "muted")
        self._empty_action = button("Nova captura", "primary", "spot")
        self._empty_action.clicked.connect(self.captureRequested.emit)
        empty_col.addWidget(self._empty_title)
        empty_col.addWidget(self._empty_text)
        empty_col.addSpacing(10)
        empty_col.addWidget(self._empty_action, 0, Qt.AlignmentFlag.AlignCenter)
        empty_col.addStretch(2)

        stack = QStackedLayout()
        stack.addWidget(self._list)
        stack.addWidget(self._empty)
        self._stack = stack

        self._status = QLabel()
        self._status.setProperty("role", "muted")
        self._status.setFont(theme.font(11.5, 400, mono=True))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(14)
        layout.addLayout(top)
        layout.addLayout(dial_line)
        layout.addLayout(stack, 1)
        layout.addWidget(self._status)

        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._search.setFocus)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        QShortcut(QKeySequence.StandardKey.Copy, self, activated=self._copy_selected)
        QShortcut(QKeySequence.StandardKey.Delete, self, activated=self._delete_selected)

        history.changed.connect(self._on_changed)
        self.refresh()

    # --- API ---------------------------------------------------------------

    def show_collection(self, collection: Collection) -> None:
        self.collection = collection
        self._tab_buttons[collection].setChecked(True)
        self.refresh()

    def refresh(self) -> None:
        query = self._search.text().strip()
        counts = self._history.counts(query)
        for collection, tab in self._tab_buttons.items():
            tab.setText(f"{tab.property('label')}  {counts[collection]}")
        entries = self._history.search(query, collection=self.collection)
        self._delegate.forget()
        self._list.clear()
        for entry in entries:
            item = QListWidgetItem()
            item.setData(ENTRY_ROLE, entry)
            item.setToolTip(" ".join(entry.text.split())[:240] or title(entry))
            self._list.addItem(item)

        if entries:
            self._stack.setCurrentWidget(self._list)
        else:
            if query:
                head, text = f'Nada encontrado para "{query}"', "A busca procura no texto que aparecia em cada captura."
            elif not self._history.enabled:
                head, text = "O histórico está desligado", 'Ligue em "Guardar histórico" no menu da bandeja.'
            else:
                head, text = EMPTY[self.collection]
            self._empty_title.setText(head)
            self._empty_text.setText(text)
            self._empty_action.setVisible(not query and self._history.enabled)
            self._stack.setCurrentWidget(self._empty)
        self._update_status()

    # --- internos ----------------------------------------------------------

    def _update_status(self) -> None:
        count = self._list.count()
        if not count or self._stack.currentWidget() is not self._list:
            self._status.setText("")
            return
        one, many = NOUNS[self.collection]
        hint = "Enter abre na leitura" if self.collection is Collection.READING else "Enter copia"
        self._status.setText(f"{count} {one if count == 1 else many}  ·  {hint}  ·  Del exclui")

    def _on_changed(self) -> None:
        if self.isVisible():
            self._debounce.start()

    def _selected(self) -> Entry | None:
        item = self._list.currentItem()
        return item.data(ENTRY_ROLE) if item else None

    def _copy_selected(self) -> None:
        if (entry := self._selected()) is not None:
            self._copy(entry)

    def _delete_selected(self) -> None:
        if (entry := self._selected()) is not None:
            self._delete(entry)

    def _activate(self, entry: Entry) -> None:
        if entry.collection is Collection.READING:
            self.readRequested.emit(QImage(str(entry.image_path)))
        else:
            self._copy(entry)

    def _copy(self, entry: Entry) -> None:
        if entry.media:
            if entry.media.exists():
                copy_file(entry.media)
                self._status.setText("Arquivo copiado, é só colar no chat ou no ticket")
            else:
                self._status.setText("O arquivo não está mais na pasta onde foi salvo")
            return
        copy_image(QImage(str(entry.image_path)))
        self._status.setText("Imagem copiada")

    def _delete(self, entry: Entry) -> None:
        effect = ("Só sai da galeria: o arquivo continua na pasta." if entry.media
                  else "A imagem e o texto lido saem da galeria.")
        text = f"“{title(entry)}”, de {entry.created_at:%d/%m às %H:%M}. {effect}"
        if confirm(self, "Excluir esta captura?", text, "Excluir captura", QImage(str(entry.thumb_path))):
            self._history.delete(entry.id)

    def _context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        entry: Entry = item.data(ENTRY_ROLE)
        menu = QMenu(self)

        def add(icon_name: str, text: str, slot, shortcut: str | None = None, color: str = theme.G300) -> QAction:
            action = menu.addAction(icons.icon(icon_name, color, size=16), text, slot)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
                action.setShortcutVisibleInContextMenu(True)
            return action

        if entry.media:
            add("copy", "Copiar arquivo", lambda: self._copy(entry), "Ctrl+C")
            add("video" if entry.kind == "video" else "gif", "Abrir",
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.media))))
            add("folder", "Mostrar na pasta", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.media.parent))))
        else:
            image = lambda: QImage(str(entry.image_path))  # noqa: E731 - carrega só se for usada
            add("copy", "Copiar imagem", lambda: self._copy(entry), "Ctrl+C")
            add("read", "Abrir na leitura", lambda: self.readRequested.emit(image()))
            add("mark", "Marcar", lambda: self.markRequested.emit(image()))
            copy_txt = add("text", "Copiar texto", lambda: copy_text(entry.text))
            copy_txt.setEnabled(bool(entry.text.strip()))
            add("folder", "Abrir imagem", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.image_path))))
        menu.addSeparator()
        add("trash", "Excluir captura…", lambda: self._delete(entry), "Del", color="#ff7a72")
        menu.exec(self._list.viewport().mapToGlobal(pos))
