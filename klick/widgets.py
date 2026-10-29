"""Componentes do Visor: botões, obturador, aviso pós-captura e confirmação."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap, QScreen
from PySide6.QtWidgets import (QAbstractButton, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton,
                               QVBoxLayout, QWidget)

from klick import icons, theme

TOAST_MS = 4000
TOAST_MARGIN = 16


def button(text: str, variant: str = "secondary", icon_name: str | None = None) -> QPushButton:
    """Botão com cara de tecla: primary (laranja, um por tela), secondary, ghost ou danger."""
    b = QPushButton(text)
    b.setProperty("variant", variant)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFont(theme.font(13, 600, 94))
    if icon_name:
        color = {"primary": theme.G950, "danger": "#ffffff"}.get(variant, theme.A300)
        b.setIcon(icons.icon(icon_name, color, size=16))
        b.setIconSize(QSize(16, 16))
    return b


def icon_button(name: str, label: str, shortcut: str | None = None, size: int = 34) -> QToolButton:
    """Botão só de ícone; o nome e o atalho aparecem no tooltip e no leitor de tela."""
    b = QToolButton()
    b.setIcon(icons.icon(name, theme.A300, hover=theme.S400, checked=theme.G950))
    b.setIconSize(QSize(18, 18))
    b.setFixedSize(size, size)
    b.setToolTip(theme.tip(label, shortcut))
    b.setAccessibleName(label)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    return b


def thumbnail(image: QImage, width: int, height: int) -> QPixmap:
    """Miniatura recortada para preencher o quadro, a partir do canto de cima à esquerda (onde fica o contexto)."""
    ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    target = QSize(round(width * ratio), round(height * ratio))
    scaled = image.scaled(target, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
    pm = QPixmap.fromImage(scaled.copy(0, 0, target.width(), target.height()))
    pm.setDevicePixelRatio(ratio)
    return pm


class ShutterButton(QAbstractButton):
    """O obturador: botão redondo laranja com anel de alumínio. A assinatura do Visor."""

    def __init__(self, diameter: int = 36, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(diameter + 6, diameter + 6)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
        c = QPointF(self.width() / 2, self.height() / 2)
        r = min(self.width(), self.height()) / 2 - 3
        p.setPen(QPen(QColor(theme.G900), 2))
        p.setBrush(QColor(theme.G800))
        p.drawEllipse(c, r + 1, r + 1)
        p.setPen(QPen(QColor(theme.A300), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r - 1, r - 1)
        inner = r * (0.56 if self.isDown() else 0.66)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.S400 if self._hover else theme.S500))
        p.drawEllipse(c, inner, inner)
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.S500), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r + 2, r + 2)


class Panel(QWidget):
    """Janela sem moldura com o painel grafite desenhado à mão (cantos e sombra de verdade)."""

    RADIUS = 4

    def __init__(self, parent: QWidget | None = None, flags=None):
        flags = flags or (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(theme.dark_panel_stylesheet())

    def panel_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.panel_rect(), self.RADIUS, self.RADIUS)
        p.fillPath(path, QColor(theme.G900))
        p.setPen(QPen(QColor(theme.G700), 1))
        p.drawPath(path)
        # brilho fino no topo, como a borda de um corpo de alumínio
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        r = self.panel_rect()
        p.drawLine(QPointF(r.left() + self.RADIUS, r.top() + 1), QPointF(r.right() - self.RADIUS, r.top() + 1))


class Toast(Panel):
    """Aviso do Klick no canto da tela: miniatura, resultado e as próximas ações à mão.

    Some sozinho em 4 s (a barra laranja mostra o tempo); com o mouse em cima, espera.
    """

    actionTriggered = Signal(str)

    def __init__(self, title: str, subtitle: str = "", image: QImage | None = None,
                 actions: list[tuple[str, str, str]] | None = None, kind: str = "ok", timeout: int = TOAST_MS):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._progress = 1.0

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 10, 10, 12)
        row.setSpacing(12)
        if image is not None and not image.isNull():
            thumb = QLabel()
            thumb.setPixmap(thumbnail(image, 96, 60))
            thumb.setFixedSize(96, 60)
            thumb.setStyleSheet(f"border: 1px solid {theme.G600}; border-radius: 2px;")
            row.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(6)
        mark = QLabel()
        color = {"ok": theme.OK, "warn": theme.WARN, "info": theme.S500}[kind]
        mark.setPixmap(icons.pixmap({"ok": "check", "warn": "warn", "info": "dot"}[kind], color, 15))
        head.addWidget(mark)
        self.title = QLabel(title)
        self.title.setFont(theme.font(13.5, 650))
        self.title.setWordWrap(True)
        head.addWidget(self.title, 1)
        text.addLayout(head)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setFont(theme.font(11, 400, mono=True))
            sub.setStyleSheet(f"color: {theme.G300};")
            sub.setWordWrap(True)
            sub.setMaximumWidth(260)
            text.addWidget(sub)
        acts = QHBoxLayout()
        acts.setContentsMargins(-6, 4, 0, 0)
        acts.setSpacing(2)
        for name, label, key in actions or []:
            b = icon_button(name, label, size=30)
            b.clicked.connect(lambda _=False, k=key: self._trigger(k))
            acts.addWidget(b)
        close = icon_button("close", "Fechar aviso", size=30)
        close.clicked.connect(self.close)
        acts.addWidget(close)
        acts.addStretch(1)
        text.addLayout(acts)
        row.addLayout(text, 1)

        self._anim = QVariantAnimation(self, startValue=1.0, endValue=0.0, duration=timeout)
        self._anim.valueChanged.connect(self._tick)
        self._anim.finished.connect(self.close)
        self.setMinimumWidth(300)
        self.adjustSize()

    def show_on(self, screen: QScreen | None) -> None:
        screen = screen or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - TOAST_MARGIN, area.bottom() - self.height() - TOAST_MARGIN)
        self.show()
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
        track = QRectF(r.left() + 1, r.bottom() - 3, r.width() - 2, 2)
        p.fillRect(track, QColor(theme.G700))
        p.fillRect(QRectF(track.left(), track.top(), track.width() * self._progress, 2), QColor(theme.S500))


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
            thumb.setStyleSheet(f"border: 1px solid {theme.G600}; border-radius: 3px;")
            body.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(6)
        heading = QLabel(title, objectName="title")
        heading.setFont(theme.font(17, 750, 112))
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
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addLayout(body)
        layout.addWidget(foot)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.G900))
        p.setPen(QPen(QColor(theme.G700), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


def confirm(parent: QWidget | None, title: str, text: str, action: str, image: QImage | None = None) -> bool:
    return ConfirmDialog(parent, title, text, action, image).exec() == QDialog.DialogCode.Accepted
