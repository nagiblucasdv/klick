"""Galeria: as capturas em quatro coleções (prints, gravações, GIFs e leitura), com busca no texto."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QModelIndex, QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QFontMetrics, QImage, QKeySequence, QPainter,
                           QPainterPath, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView,
                               QListWidget, QListWidgetItem, QMenu, QStackedLayout, QStyle, QStyledItemDelegate,
                               QVBoxLayout, QWidget)

from klick import config, icons, lens, theme
from klick.actions import copy_file, copy_image, copy_text
from klick.history import Collection, Entry, History
from klick.icon import app_icon
from klick.widgets import button, confirm, icon_button

CARD = QSize(196, 120)  # miniatura
PAD = 6  # moldura do cartão em volta da miniatura
CAPTION = 30
GAP = 12
TICK = 9  # marcas de canto (ciano) na miniatura
SIDEBAR = 214

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
FOLDER_KIND = {Collection.PRINTS: "prints", Collection.RECORDINGS: "recordings", Collection.GIFS: "gifs",
               Collection.READING: "reading"}


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
        self._title_font = theme.font(13, 500)
        self._meta_font = theme.font(11, 400, mono=True)
        self._badge_font = theme.font(10.5, 600, mono=True)
        self._cache: dict[int, QPixmap] = {}

    def sizeHint(self, option, index) -> QSize:
        return QSize(CARD.width() + 2 * PAD + GAP, CARD.height() + 2 * PAD + CAPTION + GAP)

    def forget(self) -> None:
        self._cache.clear()

    def _thumb(self, entry: Entry, ratio: float) -> QPixmap:
        pm = self._cache.get(entry.id)
        if pm is None:
            image = QImage(str(entry.thumb_path))
            pm = QPixmap(round(CARD.width() * ratio), round(CARD.height() * ratio))
            pm.fill(QColor(theme.G800))
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
        frame = QRectF(cell.left() + GAP / 2, cell.top() + GAP / 2, CARD.width() + 2 * PAD,
                       CARD.height() + 2 * PAD + CAPTION)
        card = QRectF(frame.left() + PAD, frame.top() + PAD, CARD.width(), CARD.height())
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        p.setPen(QPen(QColor(theme.S500 if selected else theme.G600 if hover else theme.G700), 2 if selected else 1))
        p.setBrush(QColor(theme.G800 if hover or selected else theme.G900))
        p.drawRoundedRect(frame.adjusted(0.5, 0.5, -0.5, -0.5), theme.WINDOW_RADIUS, theme.WINDOW_RADIUS)

        clip = QPainterPath()
        clip.addRoundedRect(card, 3, 3)
        p.setClipPath(clip)
        p.drawPixmap(card.toRect(), self._thumb(entry, p.device().devicePixelRatioF()))
        p.setClipping(False)

        # Marcas de canto, como no visor de um instrumento.
        tick = QPen(QColor(theme.CYAN), 2)
        tick.setCapStyle(Qt.PenCapStyle.SquareCap)
        p.setPen(tick)
        inner = card.adjusted(4, 4, -4, -4)
        p.drawPolyline([QPointF(inner.left(), inner.top() + TICK), inner.topLeft(), QPointF(inner.left() + TICK, inner.top())])
        p.drawPolyline([QPointF(inner.right(), inner.bottom() - TICK), inner.bottomRight(),
                        QPointF(inner.right() - TICK, inner.bottom())])

        badge = {"video": duration(entry.duration) or "MP4", "gif": "GIF"}.get(entry.kind)
        if badge:
            p.setFont(self._badge_font)
            w = QFontMetrics(self._badge_font).horizontalAdvance(badge) + 12
            box = QRectF(card.right() - w - 6, card.bottom() - 24, w, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(11, 18, 22, 220))
            p.drawRoundedRect(box, 2, 2)
            p.setPen(QColor(theme.DATA))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, badge)

        meta = when(entry)
        p.setFont(self._meta_font)
        meta_w = QFontMetrics(self._meta_font).horizontalAdvance(meta)
        line = QRectF(card.left(), card.bottom() + 6, card.width(), CAPTION - 8)
        p.setPen(QColor(theme.DATA))
        p.drawText(line, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, meta)
        p.setFont(self._title_font)
        text = QFontMetrics(self._title_font).elidedText(title(entry), Qt.TextElideMode.ElideRight,
                                                        int(card.width() - meta_w - 10))
        p.setPen(QColor(self._s.fg))
        p.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        p.restore()


class NavButton(QAbstractButton):
    """Item da barra lateral: ícone, nome da coleção e a contagem em ciano."""

    def __init__(self, icon_name: str, label: str):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setProperty("label", label)
        self.setAccessibleName(label)
        self.setText(label)
        self._icon = icon_name
        self._hover = False

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        on = self.isChecked()
        if on or self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.G700 if on else theme.G800))
            p.drawRoundedRect(r, 4, 4)
        if on:  # o "pill" do Windows 11, em laranja
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.S500))
            p.drawRoundedRect(QRectF(0, 9, 3, r.height() - 18), 1.5, 1.5)
        color = theme.PAPER if on else theme.A400
        p.drawPixmap(12, round((r.height() - 18) / 2), icons.pixmap(self._icon, theme.S400 if on else theme.G400, 18))
        label = self.property("label")
        count = self.text()[len(label):].strip()
        p.setFont(theme.font(14, 600 if on else 500))
        p.setPen(QColor(color))
        p.drawText(r.adjusted(42, 0, -40, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
        if count:
            p.setFont(theme.font(11.5, 500, mono=True))
            p.setPen(QColor(theme.DATA if on else theme.G400))
            p.drawText(r.adjusted(0, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, count)
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.CYAN), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)


class HistoryWindow(QWidget):
    captureRequested = Signal()
    readRequested = Signal(QImage)
    markRequested = Signal(QImage)
    settingsRequested = Signal()
    sqlRequested = Signal(QImage)

    def __init__(self, history: History):
        super().__init__(None, Qt.WindowType.Window)
        self._history = history
        self._scheme = theme.window_scheme()
        self.setObjectName("window")
        self.setWindowTitle("Klick: galeria")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(theme.window_stylesheet(self._scheme))
        self.resize(1120, 700)
        self.collection = Collection.PRINTS

        side = QFrame(objectName="side")
        side.setFixedWidth(SIDEBAR)
        side.setStyleSheet(f"QFrame#side {{ background: {theme.G900}; border-right: 1px solid {theme.G700}; }}")
        side_col = QVBoxLayout(side)
        side_col.setContentsMargins(10, 16, 10, 12)
        side_col.setSpacing(3)
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 10)
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(24, 24))
        name = QLabel("Klick")
        name.setFont(theme.font(20, 700, 120))
        brand.addWidget(logo)
        brand.addWidget(name)
        brand.addStretch(1)
        side_col.addLayout(brand)
        capture = button("Nova captura", "primary", "spot")
        capture.setToolTip(theme.tip("Nova captura", "PrtSc"))
        capture.clicked.connect(self.captureRequested.emit)
        side_col.addWidget(capture)
        side_col.addSpacing(12)
        section = QLabel("COLEÇÕES")
        section.setProperty("role", "muted")
        section.setFont(theme.font(10.5, 600, mono=True))
        section.setContentsMargins(8, 0, 0, 4)
        side_col.addWidget(section)

        self._tabs = QButtonGroup(self)
        self._tab_buttons: dict[Collection, NavButton] = {}
        for collection, icon_name, label in COLLECTIONS:
            tab = NavButton(icon_name, label)
            tab.setChecked(collection is self.collection)
            tab.clicked.connect(lambda _=False, c=collection: self.show_collection(c))
            self._tabs.addButton(tab)
            self._tab_buttons[collection] = tab
            side_col.addWidget(tab)
        side_col.addStretch(1)
        settings = NavButton("gear", "Configurações")
        settings.setCheckable(False)
        settings.clicked.connect(self.settingsRequested.emit)
        side_col.addWidget(settings)

        self._heading = QLabel("Prints")
        self._heading.setFont(theme.font(28, 700, 120))
        self._count = QLabel()
        self._count.setProperty("role", "data")
        self._count.setFont(theme.font(12, 500, mono=True))
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
        top.addWidget(self._heading, 0, Qt.AlignmentFlag.AlignBaseline)
        top.addWidget(self._count, 0, Qt.AlignmentFlag.AlignBaseline)
        top.addStretch(1)
        top.addWidget(self._search)
        self._folder_button = self._top_button("folder", "Abrir a pasta desta coleção")
        self._folder_button.clicked.connect(self._open_folder)
        top.addWidget(self._folder_button)

        self._delegate = CardDelegate(self._scheme, self)
        self._list = QListWidget()
        self._list.setViewMode(QListView.ViewMode.IconMode)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setMovement(QListView.Movement.Static)
        self._list.setUniformItemSizes(True)
        self._list.setGridSize(self._delegate.sizeHint(None, None))
        self._list.setItemDelegate(self._delegate)
        self._list.setMouseTracking(True)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)
        self._list.itemActivated.connect(lambda item: self._activate(item.data(ENTRY_ROLE)))
        self._list.itemSelectionChanged.connect(self._update_status)

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

        main = QVBoxLayout()
        main.setContentsMargins(22, 16, 20, 12)
        main.setSpacing(14)
        main.addLayout(top)
        main.addLayout(stack, 1)
        main.addWidget(self._status)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(side)
        layout.addLayout(main, 1)

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
            tab.update()
        self._heading.setText(self._tab_buttons[self.collection].property("label"))
        one, many = NOUNS[self.collection]
        total = counts[self.collection]
        self._count.setText(f"{total} {one if total == 1 else many}")
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
                head, text = "O histórico está desligado", 'Ligue em "Guardar histórico" nas configurações.'
            else:
                head, text = EMPTY[self.collection]
            self._empty_title.setText(head)
            self._empty_text.setText(text)
            self._empty_action.setVisible(not query and self._history.enabled)
            self._stack.setCurrentWidget(self._empty)
        self._update_status()

    # --- internos ----------------------------------------------------------

    def _top_button(self, name: str, label: str):
        b = icon_button(name, label)
        b.setIcon(icons.icon(name, theme.A300, hover=theme.DATA, size=18))
        b.setStyleSheet(f"QToolButton {{ background: {theme.G800}; border: 1px solid {theme.G700}; border-radius: 3px; }}"
                        f"QToolButton:hover {{ border-color: {theme.CYAN}; }}")
        return b

    def _open_folder(self) -> None:
        folder = config.folder(FOLDER_KIND[self.collection])
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _update_status(self) -> None:
        count = self._list.count()
        if not count or self._stack.currentWidget() is not self._list:
            self._status.setText("")
            return
        picked = len(self._list.selectedItems())
        if picked > 1:
            self._status.setText(f"{picked} selecionados  ·  Del exclui todos  ·  Esc fecha")
            return
        one, many = NOUNS[self.collection]
        hint = "Enter abre na leitura" if self.collection is Collection.READING else "Enter copia"
        self._status.setText(f"{count} {one if count == 1 else many}  ·  {hint}  ·  Ctrl+clique escolhe vários  ·  Del exclui")

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
        entries = [item.data(ENTRY_ROLE) for item in self._list.selectedItems()]
        if len(entries) > 1:
            self._delete_many(entries)
        elif entries:
            self._delete(entries[0], remove_file=True)

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

    def _delete(self, entry: Entry, remove_file: bool = True) -> None:
        when_text = f"“{title(entry)}”, de {entry.created_at:%d/%m às %H:%M}."
        if entry.media and remove_file:
            head, effect, action = ("Excluir permanentemente?", f"O arquivo {entry.media.name} é apagado do "
                                    "computador e não vai para a lixeira.", "Excluir arquivo")
        elif entry.media:
            head, effect, action = ("Remover da galeria?", "O arquivo continua na pasta.", "Remover")
        else:
            head, effect, action = ("Excluir esta captura?", "A imagem e o texto lido são apagados de vez.",
                                    "Excluir captura")
        if confirm(self, head, f"{when_text} {effect}", action, QImage(str(entry.thumb_path))):
            self._history.delete(entry.id, remove_file=remove_file)

    def _delete_many(self, entries: list[Entry]) -> None:
        files = sum(1 for e in entries if e.media)
        effect = (f" {files} arquivo{'s' if files != 1 else ''} de vídeo ou GIF também são apagados do computador."
                  if files else "")
        text = f"{len(entries)} capturas saem da galeria de vez.{effect} Não dá para desfazer."
        if confirm(self, f"Excluir {len(entries)} capturas?", text, f"Excluir {len(entries)}"):
            for entry in entries:
                self._history.delete(entry.id, remove_file=True)

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
            add("lens", "Pesquisar no Google Lens", lambda: lens.search_image(QImage(str(entry.thumb_path))))
        else:
            image = lambda: QImage(str(entry.image_path))  # noqa: E731 - carrega só se for usada
            add("copy", "Copiar imagem", lambda: self._copy(entry), "Ctrl+C")
            add("read", "Abrir na leitura", lambda: self.readRequested.emit(image()))
            add("mark", "Marcar", lambda: self.markRequested.emit(image()))
            add("sql", "Abrir no SQL", lambda: self.sqlRequested.emit(image()))
            copy_txt = add("text", "Copiar texto", lambda: copy_text(entry.text))
            copy_txt.setEnabled(bool(entry.text.strip()))
            add("lens", "Pesquisar no Google Lens", lambda: lens.search_image(image()))
            add("folder", "Abrir imagem", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.image_path))))
        menu.addSeparator()
        if entry.media:
            add("close", "Remover da galeria…", lambda: self._delete(entry, remove_file=False))
            add("trash", "Excluir permanentemente…", lambda: self._delete(entry), "Del", color="#ff7a72")
        else:
            add("trash", "Excluir permanentemente…", lambda: self._delete(entry), "Del", color="#ff7a72")
        menu.exec(self._list.viewport().mapToGlobal(pos))
