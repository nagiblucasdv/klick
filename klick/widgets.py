"""Componentes da Plumagem: botões, escolhas, interruptor, painel da pena, aviso pós-captura e confirmação."""

from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRectF, QSize,
                            Qt, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap, QScreen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from klick import icons, theme

TOAST_MS = 4000
TOAST_MARGIN = 16


def button(text: str, variant: str = "secondary", icon_name: str | None = None, on_pena: bool = False) -> QPushButton:
    """Botão reto: primary (o brilho da pena, um por tela), secondary, ghost ou danger.
    `on_pena`: o botão fica sobre a pena (fundo escuro) e o ícone é claro."""
    b = QPushButton(text)
    b.setProperty("variant", variant)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFont(theme.font(13, 600))
    if icon_name:
        if variant == "primary":
            color = theme.ON_ACCENT
        elif variant == "danger":
            color = theme.DANGER_FG
        else:
            color = theme.ON_PENA if on_pena else theme.INK_2
        b.setIcon(icons.icon(icon_name, color, size=16))
        b.setIconSize(QSize(16, 16))
    return b


def icon_button(name: str, label: str, shortcut: str | None = None, size: int = 34, on_pena: bool = False) -> QToolButton:
    """Botão só de ícone; o nome e o atalho aparecem no tooltip e no leitor de tela."""
    b = QToolButton()
    if on_pena:
        b.setIcon(icons.icon(name, theme.ON_PENA, hover="#ffffff", checked="#ffffff"))
    else:
        b.setIcon(icons.icon(name, theme.INK_2, hover=theme.ACCENT_TEXT, checked=theme.ACCENT_TEXT))
    b.setIconSize(QSize(18, 18))
    b.setFixedSize(size, size)
    b.setToolTip(theme.tip(label, shortcut))
    b.setAccessibleName(label)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    return b


class Pena(QFrame):
    """Área escura da janela (barra lateral, coluna do print). Os filhos usam as cores claras da pena."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pena")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(theme.pena_buttons())


def thumbnail(image: QImage, width: int, height: int) -> QPixmap:
    """Miniatura recortada para preencher o quadro, a partir do canto de cima à esquerda (onde fica o contexto)."""
    ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    target = QSize(round(width * ratio), round(height * ratio))
    scaled = image.scaled(target, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
    pm = QPixmap.fromImage(scaled.copy(0, 0, target.width(), target.height()))
    pm.setDevicePixelRatio(ratio)
    return pm


class Segmented(QFrame):
    """Escolha única em segmentos lado a lado (ex.: Baixa | Média | Alta)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dial")
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        self.buttons: dict[str, QToolButton] = {}
        for key, label in options:
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setChecked(key == current)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self._group.addButton(b)
            self.buttons[key] = b
            row.addWidget(b)

    @property
    def value(self) -> str:
        return next(k for k, b in self.buttons.items() if b.isChecked())

    def set_value(self, key: str) -> None:
        self.buttons[key].setChecked(True)
        self.changed.emit(key)


class Switch(QAbstractButton):
    """Interruptor liga/desliga. Ligado, o trilho ganha o brilho da pena; a bolinha desliza."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(38, 22)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=theme.ms(140), easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._move)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _move(self, value) -> None:
        self._pos = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(theme.ACCENT), 1.5) if self.hasFocus() else Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.LINE_STRONG))
        p.drawRoundedRect(r, 3, 3)
        if self._pos > 0:
            p.setOpacity(self._pos)
            p.setBrush(theme.sheen(r))
            p.drawRoundedRect(r, 3, 3)
            p.setOpacity(1.0)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(x, r.top() + 3, d, d), 2, 2)


class Panel(QWidget):
    """Janela sem moldura com o vidro escuro da pena desenhado à mão, com o corte em diagonal no canto."""

    def __init__(self, parent: QWidget | None = None, flags=None):
        flags = flags or (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(theme.panel_stylesheet())

    def panel_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = theme.feather(self.panel_rect())
        p.fillPath(path, theme.GLASS)
        p.setPen(QPen(theme.GLASS_LINE, 1))
        p.drawPath(path)


class Toast(Panel):
    """Aviso do Klick no canto da tela: miniatura, resultado e as próximas ações à mão.

    Entra deslizando do canto; some sozinho em 4 s (a linha com o brilho da pena mostra o tempo).
    Com o mouse em cima, espera.
    """

    actionTriggered = Signal(str)

    def __init__(self, title: str, subtitle: str = "", image: QImage | None = None,
                 actions: list[tuple[str, str, str]] | None = None, kind: str = "ok", timeout: int = TOAST_MS):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._progress = 1.0

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 12, 12, 14)
        row.setSpacing(12)
        if image is not None and not image.isNull():
            thumb = QLabel()
            thumb.setPixmap(thumbnail(image, 96, 60))
            thumb.setFixedSize(96, 60)
            thumb.setStyleSheet(f"border: 1px solid {theme.PENA_LINE}; border-radius: 3px;")
            row.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(6)
        mark = QLabel()
        color = {"ok": theme.SIGNAL, "warn": theme.TEMP_ON_PENA, "info": theme.SIGNAL}[kind]
        mark.setPixmap(icons.pixmap({"ok": "check", "warn": "warn", "info": "dot"}[kind], color, 15))
        head.addWidget(mark)
        self.title = QLabel(title)
        self.title.setFont(theme.font(15, 600, display=True))
        self.title.setWordWrap(True)
        head.addWidget(self.title, 1)
        text.addLayout(head)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setFont(theme.font(12.5))
            sub.setStyleSheet(f"color: {theme.ON_PENA_MUTED};")
            sub.setWordWrap(True)
            sub.setMaximumWidth(290)
            text.addWidget(sub)
        acts = QHBoxLayout()
        acts.setContentsMargins(-6, 4, 0, 0)
        acts.setSpacing(2)
        for name, label, key in actions or []:
            b = icon_button(name, label, size=30, on_pena=True)
            b.clicked.connect(lambda _=False, k=key: self._trigger(k))
            acts.addWidget(b)
        close = icon_button("close", "Fechar aviso", size=30, on_pena=True)
        close.clicked.connect(self.close)
        acts.addWidget(close)
        acts.addStretch(1)
        text.addLayout(acts)
        row.addLayout(text, 1)

        self._anim = QVariantAnimation(self, startValue=1.0, endValue=0.0, duration=timeout)
        self._anim.valueChanged.connect(self._tick)
        self._anim.finished.connect(self.close)
        self._enter: QParallelAnimationGroup | None = None
        self.setMinimumWidth(340)
        self.adjustSize()

    def show_on(self, screen: QScreen | None) -> None:
        screen = screen or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        end = QPoint(area.right() - self.width() - TOAST_MARGIN, area.bottom() - self.height() - TOAST_MARGIN)
        duration = theme.ms(220)
        self.move(end + QPoint(28, 0) if duration else end)
        self.setWindowOpacity(0.0 if duration else 1.0)
        self.show()
        if duration:
            self._enter = QParallelAnimationGroup(self)
            for prop, start, stop in ((b"pos", end + QPoint(28, 0), end), (b"windowOpacity", 0.0, 1.0)):
                anim = QPropertyAnimation(self, prop, self)
                anim.setStartValue(start)
                anim.setEndValue(stop)
                anim.setDuration(duration)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._enter.addAnimation(anim)
            self._enter.start()
        self._anim.start()

    def enterEvent(self, event) -> None:
        self._anim.pause()

    def leaveEvent(self, event) -> None:
        self._anim.resume()

    def _trigger(self, key: str) -> None:
        self.actionTriggered.emit(key)
        self.close()

    def _tick(self, value) -> None:
        self._progress = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        r = self.panel_rect()
        track = QRectF(r.left() + 12, r.bottom() - 4, r.width() - 24, 2)
        p.fillRect(track, QColor(255, 255, 255, 26))
        p.fillRect(QRectF(track.left(), track.top(), track.width() * self._progress, 2), theme.sheen(track))


class ConfirmDialog(QDialog):
    """Confirmação só para o que não tem volta. O botão diz exatamente o que vai acontecer."""

    def __init__(self, parent: QWidget | None, title: str, text: str, confirm: str,
                 image: QImage | None = None, icon_name: str = "trash"):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("klickDialog")
        self.setStyleSheet(theme.app_stylesheet())
        self.setModal(True)
        self.setMinimumWidth(400)

        body = QHBoxLayout()
        body.setContentsMargins(18, 18, 18, 18)
        body.setSpacing(14)
        if image is not None and not image.isNull():
            thumb = QLabel()
            thumb.setPixmap(thumbnail(image, 92, 58))
            thumb.setFixedSize(92, 58)
            thumb.setStyleSheet(f"border: 1px solid {theme.LINE}; border-radius: 3px;")
            body.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(6)
        heading = QLabel(title, objectName="title")
        heading.setFont(theme.font(19, 600, display=True))
        message = QLabel(text)
        message.setWordWrap(True)
        words.addWidget(heading)
        words.addWidget(message)
        words.addStretch(1)
        body.addLayout(words, 1)

        foot = QFrame(objectName="dialogFoot")
        row = QHBoxLayout(foot)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(8)
        hint = QLabel(f"{theme.tip('', 'Esc')} cancela", objectName="hint")
        row.addWidget(hint)
        row.addStretch(1)
        cancel = button("Cancelar", "ghost")
        cancel.clicked.connect(self.reject)
        cancel.setDefault(True)
        ok = button(confirm, "danger", icon_name)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 3, 1, 1)
        layout.setSpacing(0)
        layout.addLayout(body)
        layout.addWidget(foot)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        r = QRectF(self.rect())
        p.fillRect(r, QColor(theme.SURFACE))
        p.fillRect(QRectF(0, 0, r.width(), 3), theme.sheen(QRectF(0, 0, r.width(), 3)))  # o fio de brilho em cima
        p.setPen(QPen(QColor(theme.LINE_STRONG), 1))
        p.drawRect(r.adjusted(0, 0, -1, -1))


def confirm(parent: QWidget | None, title: str, text: str, action: str, image: QImage | None = None) -> bool:
    return ConfirmDialog(parent, title, text, action, image).exec() == QDialog.DialogCode.Accepted
