"""Galeria: as capturas em coleções (prints, gravações, GIFs, leituras e análises), com busca no texto.

Barra lateral na pena (escura): as coleções, a biblioteca de consultas, o filtro do que está só na
galeria e as configurações; um marcador desliza até o item escolhido. Cada cartão mostra se a captura está só na galeria (e em
quantos dias some) ou já guardada na pasta.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import (QEasingCurve, QModelIndex, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, QUrl,
                            Signal)
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QFontMetrics, QImage, QKeySequence, QPainter,
                           QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QHBoxLayout, QLabel, QLineEdit, QListView,
                               QListWidget, QListWidgetItem, QMenu, QSizePolicy, QStackedLayout, QStyle,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from klick import __author__, config, icons, lens, theme
from klick.actions import copy_file, copy_image, copy_text
from klick.history import FOLDER_KIND, Collection, Entry, History
from klick.library import Library
from klick.library_ui import LibraryPage
from klick.icon import app_icon
from klick.widgets import Pena, button, confirm

CARD = QSize(212, 124)  # miniatura
CAPTION = 52
GAP = 14
RADIUS = 14
SIDEBAR = 232

COLLECTIONS = [
    (None, "Tudo", "spot"),
    (Collection.PRINTS, "Prints", "image"),
    (Collection.RECORDINGS, "Gravações", "video"),
    (Collection.GIFS, "GIFs", "gif"),
    (Collection.READING, "Leituras", "read"),
    (Collection.ANALYSIS, "Análises", "analysis"),
]
EMPTY = {
    None: ("Nada aqui ainda", "Aperte PrtSc, selecione uma área e copie."),
    Collection.PRINTS: ("Nenhum print ainda", "Aperte PrtSc, selecione uma área e copie ou salve."),
    Collection.RECORDINGS: ("Nenhuma gravação ainda", "Aperte o atalho de gravar, escolha a área e Vídeo."),
    Collection.GIFS: ("Nenhum GIF ainda", "Aperte o atalho de gravar, escolha a área e GIF."),
    Collection.READING: ("Nada lido ainda", "Escolha Ler na seleção ou use o atalho de ler texto."),
    Collection.ANALYSIS: ("Nenhuma análise ainda", "Escolha Análise na seleção sobre um SQL, JSON ou tabela."),
}
NOUNS = {None: ("item", "itens"), Collection.PRINTS: ("print", "prints"),
         Collection.RECORDINGS: ("gravação", "gravações"), Collection.GIFS: ("GIF", "GIFs"),
         Collection.READING: ("leitura", "leituras"), Collection.ANALYSIS: ("análise", "análises")}
ENTRY_ROLE = Qt.ItemDataRole.UserRole


def when(entry: Entry) -> str:
    day = entry.created_at.date()
    if day == date.today():
        return f"Hoje {entry.created_at:%H:%M}"
    if day == date.today() - timedelta(days=1):
        return f"Ontem {entry.created_at:%H:%M}"
    return entry.created_at.strftime("%d/%m %H:%M")


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


def status(entry: Entry, days: int) -> tuple[str, bool]:
    """Selo do cartão: ("some em 5 dias", True) se é temporário, ("na pasta", False) se guardado."""
    left = entry.expires_in(days)
    if left is None:
        return ("só na galeria", True) if entry.temp else ("na pasta", False)
    return ("some hoje" if left == 0 else f"some em {left} dia{'s' if left != 1 else ''}"), True


class CardDelegate(QStyledItemDelegate):
    """Cartão: miniatura em cima, título, data e o selo (temporário ou na pasta). Com o mouse em cima, a borda
    acende; escolhido, ganha o brilho da pena."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title_font = theme.font(13, 600)
        self._meta_font = theme.font(12)
        self._badge_font = theme.font(12, 600, display=True)
        self._cache: dict[int, QPixmap] = {}
        self.days = config.temp_days()

    def sizeHint(self, option, index) -> QSize:
        return QSize(CARD.width() + GAP, CARD.height() + CAPTION + GAP)

    def forget(self) -> None:
        self._cache.clear()
        self.days = config.temp_days()

    def _thumb(self, entry: Entry, ratio: float) -> QPixmap:
        pm = self._cache.get(entry.id)
        if pm is None:
            image = QImage(str(entry.thumb_path))
            pm = QPixmap(round(CARD.width() * ratio), round(CARD.height() * ratio))
            pm.fill(QColor(theme.SUNKEN))
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
        frame = QRectF(cell.left() + GAP / 2, cell.top() + GAP / 2, CARD.width(), CARD.height() + CAPTION)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        lifted = hover or selected
        if lifted:
            shadow = theme.feather(frame.translated(0, 3), cut=10)
            p.fillPath(shadow, QColor(16, 22, 29, 30))
        card = theme.feather(frame, cut=10)
        p.fillPath(card, QColor(theme.SURFACE))
        p.setClipPath(card)
        thumb = QRectF(frame.left(), frame.top(), CARD.width(), CARD.height())
        p.drawPixmap(thumb.toRect(), self._thumb(entry, p.device().devicePixelRatioF()))
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if selected:
            p.setPen(QPen(theme.sheen(frame), 2))
        else:
            p.setPen(QPen(QColor(theme.ACCENT if hover else theme.LINE), 1))
        p.drawPath(card)

        badge = {"video": duration(entry.duration) or "MP4", "gif": "GIF"}.get(entry.kind)
        if badge:
            p.setFont(self._badge_font)
            w = QFontMetrics(self._badge_font).horizontalAdvance(badge) + 14
            box = QRectF(thumb.right() - w - 8, thumb.bottom() - 26, w, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(18, 24, 33, 210))
            p.drawRoundedRect(box, 3, 3)
            p.setPen(QColor("#ffffff"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, badge)

        text = QRectF(frame.left() + 12, thumb.bottom() + 8, frame.width() - 24, 18)
        p.setFont(self._title_font)
        p.setPen(QColor(theme.INK))
        p.drawText(text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(self._title_font).elidedText(title(entry), Qt.TextElideMode.ElideRight,
                                                             int(text.width())))
        meta = QRectF(text.left(), text.bottom() + 3, text.width(), 18)
        label, temp = status(entry, self.days)
        p.setFont(self._badge_font)
        bw = QFontMetrics(self._badge_font).horizontalAdvance(label) + 14
        pill = QRectF(meta.right() - bw, meta.top(), bw, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.TEMP_BG if temp else theme.ACCENT_SOFT))
        p.drawRoundedRect(pill, 3, 3)
        p.setPen(QColor(theme.TEMP_FG if temp else theme.ACCENT_TEXT))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, label)
        p.setFont(self._meta_font)
        p.setPen(QColor(theme.MUTED))
        p.drawText(meta.adjusted(0, 0, -bw - 6, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   when(entry))
        p.restore()


class NavItem(QAbstractButton):
    """Item da barra lateral: ícone, nome e contagem. O fundo do escolhido é o marcador (NavMarker), que desliza."""

    def __init__(self, label: str, icon_name: str, color: str = theme.ON_PENA_MUTED, on_color: str = "#ffffff"):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(label)
        self.label = label
        self.count: int | None = None
        self._icon = icons.pixmap(icon_name, color, 18)
        self._icon_on = icons.pixmap(icon_name, on_color, 18)
        self._color, self._on_color = color, on_color
        self._hover = False

    def set_count(self, count: int | None) -> None:
        self.count = count
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        on = self.isChecked()
        if self._hover and not on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 12))
            p.drawRoundedRect(r, 3, 3)
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.SIGNAL), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 3, 3)
        p.drawPixmap(14, (self.height() - 18) // 2, self._icon_on if on or self._hover else self._icon)
        p.setFont(theme.font(13.5, 600 if on else 400))
        p.setPen(QColor(self._on_color if on else theme.ON_PENA if self._color == theme.ON_PENA_MUTED else self._color))
        p.drawText(QRectF(42, 0, r.width() - 80, r.height()), Qt.AlignmentFlag.AlignVCenter, self.label)
        if self.count is not None:
            p.setFont(theme.font(13, display=True))
            p.setPen(QColor(theme.ON_PENA_MUTED))
            p.drawText(QRectF(0, 0, r.width() - 12, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, str(self.count))


class NavMarker(QWidget):
    """Fundo do item escolhido da barra lateral, com o fio de brilho à esquerda. Desliza de um item ao outro."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def go(self, target: QWidget, animate: bool = True) -> None:
        goal = QRect(target.geometry())
        self._anim.stop()
        if animate and self.isVisible() and theme.ms(260):
            self._anim.setDuration(theme.ms(260))
            self._anim.setStartValue(self.geometry())
            self._anim.setEndValue(goal)
            self._anim.start()
        else:
            self.setGeometry(goal)
        self.show()
        self.lower()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(r, 3, 3)
        bar = QRectF(r.left(), r.top() + 8, 3, r.height() - 16)
        p.setBrush(theme.sheen(QRectF(0, bar.top(), r.height(), bar.height())))
        p.drawRect(bar)


class HistoryWindow(QWidget):
    captureRequested = Signal()
    recordRequested = Signal()
    readRequested = Signal(QImage)
    markRequested = Signal(QImage)
    settingsRequested = Signal(str)  # seção para abrir ("" = do começo)
    sqlRequested = Signal(QImage)

    def __init__(self, history: History, library: Library | None = None):
        super().__init__(None, Qt.WindowType.Window)
        self._history = history
        self._library = library if library is not None else Library(config.library_path())
        self.library_mode = False  # a página Consultas está aberta (no lugar dos cartões)
        self.setObjectName("window")
        self.setWindowTitle("Klick: galeria")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(theme.window_stylesheet() + f"""
            QLineEdit#search {{ padding: 8px 14px; font-size: 14px; }}
            QLineEdit#search:focus {{ border: 1px solid {theme.ACCENT}; }}""")
        self.resize(1180, 760)
        self.collection: Collection | None = Collection.PRINTS
        self.temp_only = False
        keys = {name_: config.hotkey_label(combo) for name_, combo in config.hotkeys().items()}

        # --- barra lateral na pena: marca, ações, coleções, prazo e configurações ---
        side = Pena()
        side.setFixedWidth(SIDEBAR)
        self._marker = NavMarker(side)
        nav = QVBoxLayout(side)
        nav.setContentsMargins(12, 16, 12, 12)
        nav.setSpacing(2)
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(28, 28))
        name = QLabel("Klick")
        name.setFont(theme.font(21, 600, display=True))
        brand.addWidget(logo)
        brand.addWidget(name)
        brand.addStretch(1)
        nav.addLayout(brand)
        nav.addSpacing(16)
        capture = button("Capturar", "primary", "spot")
        capture.setToolTip(theme.tip("Capturar uma área", keys["capture"]))
        capture.clicked.connect(self.captureRequested.emit)
        record = button("Gravar vídeo ou GIF", "secondary", "rec", on_pena=True)
        record.setIcon(icons.icon("rec", theme.REC, size=16))
        record.setToolTip(theme.tip("Gravar vídeo ou GIF", keys["record"]))
        record.clicked.connect(self.recordRequested.emit)
        nav.addWidget(capture)
        nav.addSpacing(6)
        nav.addWidget(record)
        nav.addSpacing(18)
        nav.addWidget(self._section("Coleções"))

        self._tabs = QButtonGroup(self)
        self._tab_buttons: dict[Collection | None, NavItem] = {}
        for collection, label, icon_name in COLLECTIONS:
            item = NavItem(label, icon_name)
            item.setChecked(collection is self.collection)
            item.clicked.connect(lambda _=False, c=collection: self.show_collection(c))
            item.toggled.connect(lambda on, i=item: on and self._marker.go(i))
            self._tabs.addButton(item)
            self._tab_buttons[collection] = item
            nav.addWidget(item)
        nav.addSpacing(14)
        nav.addWidget(self._section("Biblioteca"))
        self._library_item = NavItem("Consultas", "sql")
        self._library_item.setToolTip("Todas as consultas SQL que você guardou, numa página só")
        self._library_item.clicked.connect(self.show_library)
        self._library_item.toggled.connect(lambda on: on and self._marker.go(self._library_item))
        self._tabs.addButton(self._library_item)
        nav.addWidget(self._library_item)
        nav.addSpacing(14)
        nav.addWidget(self._section("Prazo"))
        self._temp_filter = NavItem("Só na galeria", "clock", theme.TEMP_ON_PENA, theme.TEMP_ON_PENA)
        self._temp_filter.toggled.connect(self._toggle_temp)
        nav.addWidget(self._temp_filter)
        self._temp_note = QLabel(wordWrap=True)
        self._temp_note.setProperty("role", "muted")
        self._temp_note.setFont(theme.font(12))
        self._temp_note.setContentsMargins(14, 2, 8, 0)
        nav.addWidget(self._temp_note)
        nav.addStretch(1)
        folder = NavItem("Abrir a pasta", "folder")
        folder.setCheckable(False)
        folder.setToolTip("Abrir a pasta desta coleção")
        folder.clicked.connect(self._open_folder)
        settings = NavItem("Configurações", "gear")
        settings.setCheckable(False)
        settings.clicked.connect(lambda: self.settingsRequested.emit(""))
        nav.addWidget(folder)
        nav.addWidget(settings)
        sign = QLabel(f"criado por {__author__}")
        sign.setProperty("role", "muted")
        sign.setFont(theme.font(12))
        sign.setContentsMargins(14, 8, 0, 0)
        nav.addWidget(sign)

        # --- área principal: título da coleção, busca e os cartões ---
        self._heading = QLabel()
        self._heading.setFont(theme.font(28, 600, display=True))
        self._search = QLineEdit(objectName="search", placeholderText="Buscar no texto das capturas, ex.: erro 500")
        self._search.setClearButtonEnabled(True)
        self._search.addAction(icons.icon("search", theme.MUTED, size=16), QLineEdit.ActionPosition.LeadingPosition)
        self._search.setMinimumWidth(280)
        self._search.setMaximumWidth(440)
        self._search.setAccessibleName("Buscar")
        self._debounce = QTimer(self, singleShot=True, interval=200, timeout=self.refresh)
        self._search.textChanged.connect(self._debounce.start)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(self._heading)
        head.addStretch(1)
        head.addWidget(self._search, 1)

        self._delegate = CardDelegate(self)
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
        self._list.viewport().setAutoFillBackground(False)

        self._empty = QWidget()
        empty_col = QVBoxLayout(self._empty)
        empty_col.addStretch(1)
        self._empty_title = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._empty_title.setFont(theme.font(22, 600, display=True))
        self._empty_text = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self._empty_text.setProperty("role", "muted")
        self._empty_action = button("Capturar", "primary", "spot")
        self._empty_action.clicked.connect(self.captureRequested.emit)
        empty_col.addWidget(self._empty_title)
        empty_col.addWidget(self._empty_text)
        empty_col.addSpacing(10)
        empty_col.addWidget(self._empty_action, 0, Qt.AlignmentFlag.AlignCenter)
        empty_col.addStretch(2)

        stack = QStackedLayout()
        stack.addWidget(self._list)
        stack.addWidget(self._empty)
        self._library_page = LibraryPage(self._library)
        stack.addWidget(self._library_page)
        self._stack = stack

        self._status = QLabel()
        self._status.setProperty("role", "muted")
        self._status.setFont(theme.font(12, 400))
        self._library_page.message.connect(self._status.setText)

        main = QVBoxLayout()
        main.setContentsMargins(22, 16, 18, 12)
        main.setSpacing(14)
        main.addLayout(head)
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
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self._keep_selected)
        QShortcut(QKeySequence.StandardKey.Delete, self, activated=self._delete_selected)

        history.changed.connect(self._on_changed)
        self._library.changed.connect(lambda: self._library_item.set_count(self._library.count()))
        self.refresh()

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "section")
        label.setContentsMargins(14, 0, 0, 4)
        return label

    def _nav_item(self) -> NavItem:
        return self._library_item if self.library_mode else self._tab_buttons[self.collection]

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._marker.go(self._nav_item(), animate=False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._marker.isVisible():
            self._marker.go(self._nav_item(), animate=False)

    # --- API ---------------------------------------------------------------

    def show_collection(self, collection: Collection | None) -> None:
        self.collection = collection
        self.library_mode = False
        self._tab_buttons[collection].setChecked(True)
        self.refresh()

    def show_library(self, query_id: int | None = None) -> None:
        """Abre a página Consultas (e, se pedido, já com uma consulta escolhida)."""
        self.library_mode = True
        self._library_item.setChecked(True)
        self.refresh()
        if query_id is not None:
            self._library_page.select(query_id)

    def refresh(self) -> None:
        query = self._search.text().strip()
        self._library_item.set_count(self._library.count())
        self._search.setPlaceholderText("Buscar nas consultas, no nome ou no texto" if self.library_mode
                                        else "Buscar no texto das capturas, ex.: erro 500")
        if self.library_mode:
            self._heading.setText("Consultas")
            self._stack.setCurrentWidget(self._library_page)
            self._library_page.refresh(query)
            count = self._library.count()
            self._status.setText(f"{count} consulta{'s' if count != 1 else ''} guardada{'s' if count != 1 else ''}. "
                                 "O que você edita é guardado sozinho; duplo clique ou Ctrl+C copia.")
            return
        counts = self._history.counts(query)
        for collection, item in self._tab_buttons.items():
            item.set_count(sum(counts.values()) if collection is None else counts[collection])
        temp = self._history.temp_count()
        days = config.temp_days()
        self._temp_filter.set_count(temp)
        self._temp_note.setText(f"Some em {days} dias se não for guardado na pasta." if days
                                else "Nada some sozinho.")
        self._heading.setText(next(label for c, label, _ in COLLECTIONS if c is self.collection)
                              + (", só na galeria" if self.temp_only else ""))
        entries = self._history.search(query, collection=self.collection, temp_only=self.temp_only)
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
            elif self.temp_only:
                head, text = "Nada só na galeria", "Tudo desta coleção já está guardado na pasta."
            elif not self._history.enabled:
                head, text = "O histórico está desligado", 'Ligue em "Guardar histórico" nas configurações.'
            else:
                head, text = EMPTY[self.collection]
            self._empty_title.setText(head)
            self._empty_text.setText(text)
            self._empty_action.setVisible(not query and not self.temp_only and self._history.enabled)
            self._stack.setCurrentWidget(self._empty)
        self._update_status()

    # --- internos ----------------------------------------------------------

    def _toggle_temp(self, on: bool) -> None:
        self.temp_only = on
        if self.library_mode and on:
            self.show_collection(self.collection)  # o prazo vale para as capturas, não para as consultas
            return
        self.refresh()

    def _open_folder(self) -> None:
        if self.library_mode:
            self._open(config.folder("reading"))
            return
        self._open(config.folder(FOLDER_KIND[self.collection]) if self.collection else config.save_dir())

    @staticmethod
    def _open(folder) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _update_status(self) -> None:
        if self.library_mode:
            return
        count = self._list.count()
        if not count or self._stack.currentWidget() is not self._list:
            self._status.setText("")
            return
        picked = len(self._list.selectedItems())
        if picked > 1:
            self._status.setText(f"{picked} selecionados. Ctrl+S guarda na pasta, Del exclui.")
            return
        one, many = NOUNS[self.collection]
        days = config.temp_days()
        rule = f"O que está só na galeria some em {days} dias." if days else "Nada some sozinho."
        self._status.setText(f"{count} {one if count == 1 else many}. {rule} Ctrl+S guarda na pasta.")

    def _on_changed(self) -> None:
        if self.isVisible():
            self._debounce.start()

    def _selected(self) -> Entry | None:
        item = self._list.currentItem()
        return item.data(ENTRY_ROLE) if item else None

    def _copy_selected(self) -> None:
        if self.library_mode:
            self._library_page.copy()
        elif (entry := self._selected()) is not None:
            self._copy(entry)

    def _keep_selected(self) -> None:
        if self.library_mode:
            return  # as consultas já se guardam sozinhas
        entries = [item.data(ENTRY_ROLE) for item in self._list.selectedItems()]
        self._keep([e for e in entries if e.temp])

    def _keep(self, entries: list[Entry]) -> None:
        if not entries:
            self._status.setText("Nada para guardar: os selecionados já estão na pasta")
            return
        try:
            paths = [self._history.keep(e.id) for e in entries]
        except OSError as exc:
            self._status.setText(f"Não deu para guardar: {exc}")
            return
        done = [p for p in paths if p]
        if len(done) == 1:
            self._status.setText(f"Guardado em {done[0].parent.name}/{done[0].name}")
        else:
            self._status.setText(f"{len(done)} capturas guardadas na pasta")

    def _delete_selected(self) -> None:
        if self.library_mode:
            self._library_page.delete_current()
            return
        entries = [item.data(ENTRY_ROLE) for item in self._list.selectedItems()]
        if len(entries) > 1:
            self._delete_many(entries)
        elif entries:
            self._delete(entries[0], remove_file=True)

    def _activate(self, entry: Entry) -> None:
        if entry.collection is Collection.READING:
            self.readRequested.emit(QImage(str(entry.image_path)))
        elif entry.collection is Collection.ANALYSIS:
            self.sqlRequested.emit(QImage(str(entry.image_path)))
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
            head, effect, action = ("Excluir esta captura?", "Sai da galeria de vez. Uma cópia guardada na pasta "
                                    "continua lá.", "Excluir captura")
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

        def add(icon_name: str, text: str, slot, shortcut: str | None = None, color: str = theme.INK_2) -> QAction:
            return menu.addAction(icons.icon(icon_name, color, size=16), f"{text}\t{shortcut}" if shortcut else text,
                                  slot)

        if entry.temp:
            add("keep", "Guardar na pasta", lambda: self._keep([entry]), "Ctrl+S", color=theme.ACCENT_TEXT)
            menu.addSeparator()
        if entry.media:
            add("copy", "Copiar arquivo", lambda: self._copy(entry), "Ctrl+C")
            add("video" if entry.kind == "video" else "gif", "Abrir",
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.media))))
            add("folder", "Mostrar na pasta", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.media.parent))))
            add("lens", "Pesquisar no Google Lens", lambda: lens.search_image(QImage(str(entry.thumb_path))))
        else:
            image = lambda: QImage(str(entry.image_path))  # noqa: E731 - carrega só se for usada
            add("copy", "Copiar imagem", lambda: self._copy(entry), "Ctrl+C")
            add("mark", "Editar imagem", lambda: self.markRequested.emit(image()))
            add("read", "Abrir na leitura", lambda: self.readRequested.emit(image()))
            add("analysis", "Abrir na Análise", lambda: self.sqlRequested.emit(image()))
            copy_txt = add("text", "Copiar texto", lambda: copy_text(entry.text))
            copy_txt.setEnabled(bool(entry.text.strip()))
            add("lens", "Pesquisar no Google Lens", lambda: lens.search_image(image()))
            if entry.saved:
                add("folder", "Mostrar na pasta",
                    lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.saved.parent))))
        menu.addSeparator()
        if entry.media:
            add("close", "Remover da galeria…", lambda: self._delete(entry, remove_file=False))
        add("trash", "Excluir permanentemente…", lambda: self._delete(entry), "Del", color=theme.DANGER_FG)
        menu.exec(self._list.viewport().mapToGlobal(pos))
