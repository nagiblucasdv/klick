"""Identidade Plumagem: cores, fontes, formas e folhas de estilo do Klick.

Vem do corvo do ícone. A moldura (barras laterais, painéis sobre a tela, avisos, menus) é negro-azulada
como a pena; o conteúdo é claro, para ler bem. O brilho furta-cor da pena (verde-água, índigo, violeta)
aparece só no que está ativo: a seleção, o foco, a ação principal. Cantos retos de 4 px, e os painéis
ganham um corte em diagonal no canto de cima, como a ponta de uma pena.

Bahnschrift (a fonte técnica do Windows) nos títulos, números e rótulos; Segoe UI no texto corrido;
Consolas no código. As três vêm com o sistema e ficam nítidas em qualquer tamanho.
"""

from __future__ import annotations

import sys
from functools import cache

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainterPath, QPalette

FAMILY = "Segoe UI"
DISPLAY = "Bahnschrift"
MONO = "Consolas"

# Moldura: a pena.
PENA, PENA_2, PENA_3, PENA_LINE = "#121821", "#1a2230", "#243042", "#2a3546"
ON_PENA, ON_PENA_MUTED = "#e9eef3", "#9aa6b2"
# Conteúdo claro.
PAGE, SURFACE, FIELD, SUNKEN = "#f3f5f7", "#ffffff", "#ffffff", "#e9edf1"
LINE, LINE_STRONG = "#d6dde4", "#c3ccd5"
INK, INK_2, MUTED, FAINT = "#10161d", "#2b3540", "#5a6672", "#8b96a1"
# Ação: índigo; o brilho furta-cor só no que está ativo.
ACCENT, ACCENT_HOVER, ACCENT_TEXT, ACCENT_SOFT = "#4b55e0", "#5c66f0", "#3c45c4", "#e7e9fd"
ON_ACCENT = "#ffffff"
SHEEN = ("#22bfb0", "#5c68f2", "#a35ff5")
SIGNAL = "#2bd4c4"  # foco e cantos da seleção sobre a tela
# Estados.
OK, REC, WARN = "#1f8a5b", "#e5484d", "#9a5b00"
TEMP_FG, TEMP_BG, TEMP_ON_PENA = "#9a5b00", "#fbeed6", "#f0b34a"
DANGER_BG, DANGER_FG, DANGER_LINE = "#fdecea", "#b42318", "#f4c7c1"

GLASS = QColor(18, 24, 33, 236)  # painéis por cima da tela congelada
GLASS_LINE = QColor(255, 255, 255, 34)
DIM = QColor(10, 14, 20, 125)  # escurecimento fora da seleção

RADIUS = 4  # tudo: botões, campos, cartões
CUT = 12  # corte em diagonal no canto de cima, à direita, dos painéis e cartões


def apply(app: QGuiApplication) -> None:
    """Esquema claro no conteúdo (mesmo com o Windows no modo escuro) e a paleta da Plumagem no app todo."""
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, PAGE), (QPalette.ColorRole.Base, FIELD),
                        (QPalette.ColorRole.AlternateBase, PAGE), (QPalette.ColorRole.Button, SURFACE),
                        (QPalette.ColorRole.WindowText, INK), (QPalette.ColorRole.Text, INK),
                        (QPalette.ColorRole.ButtonText, INK), (QPalette.ColorRole.PlaceholderText, FAINT),
                        (QPalette.ColorRole.Highlight, ACCENT_SOFT), (QPalette.ColorRole.HighlightedText, ACCENT_TEXT),
                        (QPalette.ColorRole.ToolTipBase, PENA), (QPalette.ColorRole.ToolTipText, ON_PENA),
                        (QPalette.ColorRole.Link, ACCENT_TEXT), (QPalette.ColorRole.Mid, LINE_STRONG),
                        (QPalette.ColorRole.Midlight, LINE), (QPalette.ColorRole.Light, SURFACE)):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setFont(font(13))
    app.setStyleSheet(app_stylesheet())
    if sys.platform == "win32":
        app._title_bars = _TitleBars(app)
        app.installEventFilter(app._title_bars)


class _TitleBars(QObject):
    """Barra de título da cor da pena, com o texto claro: a moldura da janela é a mesma das barras."""

    def eventFilter(self, obj, event) -> bool:
        if (event.type() == QEvent.Type.Show and obj.isWidgetType() and obj.isWindow()
                and obj.windowType() in (Qt.WindowType.Window, Qt.WindowType.Dialog)
                and not obj.windowFlags() & Qt.WindowType.FramelessWindowHint):
            title_bar(int(obj.winId()))
        return False


def title_bar(hwnd: int) -> None:
    import ctypes

    def bgr(color: str) -> int:
        c = QColor(color)
        return c.red() | c.green() << 8 | c.blue() << 16

    dwm = ctypes.windll.dwmapi
    # 20: modo escuro (os botões de fechar ficam claros); 35 e 36: cor do fundo e do texto; 34: borda.
    for attribute, value in ((20, 1), (35, bgr(PENA)), (36, bgr(ON_PENA)), (34, bgr(PENA))):
        v = ctypes.c_int(value)
        dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v))


def font(px: float, weight: int = 400, display: bool = False, mono: bool = False) -> QFont:
    """Fonte em pixels. `display` é a Bahnschrift (títulos, números, rótulos); `mono`, a Consolas."""
    f = QFont(MONO if mono else DISPLAY if display else FAMILY)
    f.setPixelSize(round(px))
    # Segoe UI e Bahnschrift têm 300, 400, 600 e 700 de verdade: um peso no meio seria inventado e borraria.
    f.setWeight(QFont.Weight(300 if weight < 350 else 400 if weight < 550 else 600 if weight < 650 else 700))
    return f


def motion() -> bool:
    """False se o Windows está com as animações desligadas (Acessibilidade > Efeitos visuais)."""
    if sys.platform != "win32":
        return True
    import ctypes

    value = ctypes.c_int(1)
    if not ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0):  # SPI_GETCLIENTAREAANIMATION
        return True
    return bool(value.value)


def ms(duration: int) -> int:
    """Duração de animação, ou 0 se o Windows pede sem animação."""
    return duration if motion() else 0


def sheen(rect: QRectF, alpha: int = 255) -> QLinearGradient:
    """O brilho furta-cor da pena, da esquerda para a direita de `rect`."""
    g = QLinearGradient(rect.topLeft(), rect.topRight())
    for stop, color in zip((0.0, 0.55, 1.0), SHEEN):
        c = QColor(color)
        c.setAlpha(alpha)
        g.setColorAt(stop, c)
    return g


def feather(rect: QRectF, cut: float = CUT, radius: float = RADIUS) -> QPainterPath:
    """Retângulo com cantos de 4 px e o canto de cima, à direita, cortado em diagonal (a ponta da pena)."""
    r, c = rect, min(cut, rect.width() / 3, rect.height() / 3)
    path = QPainterPath()
    path.moveTo(r.left() + radius, r.top())
    path.lineTo(r.right() - c, r.top())
    path.lineTo(r.right(), r.top() + c)
    path.lineTo(r.right(), r.bottom() - radius)
    path.quadTo(QPointF(r.right(), r.bottom()), QPointF(r.right() - radius, r.bottom()))
    path.lineTo(r.left() + radius, r.bottom())
    path.quadTo(QPointF(r.left(), r.bottom()), QPointF(r.left(), r.bottom() - radius))
    path.lineTo(r.left(), r.top() + radius)
    path.quadTo(QPointF(r.left(), r.top()), QPointF(r.left() + radius, r.top()))
    path.closeSubpath()
    return path


@cache
def _kbd_style() -> str:
    return (f"font-family:'{DISPLAY}'; font-size:11px; color:{ON_PENA}; background:{PENA_3};"
            f" padding:0 4px; border-radius:3px;")


def tip(label: str, shortcut: str | None = None) -> str:
    """Texto de tooltip com o atalho em destaque: "Ler o texto  Ctrl T"."""
    if not shortcut:
        return label
    return f"{label}&nbsp;&nbsp;<span style=\"{_kbd_style()}\">&nbsp;{shortcut}&nbsp;</span>"


def sheen_qss() -> str:
    stops = ", ".join(f"stop:{s} {c}" for s, c in zip((0, 0.55, 1), SHEEN))
    return f"qlineargradient(x1:0, y1:0, x2:1, y2:0, {stops})"


# Botões. Primário: o brilho da pena (um por tela). Os outros, retos e discretos.
_BUTTONS = f"""
QPushButton {{ min-height: 34px; padding: 0 14px; border-radius: {RADIUS}px; border: 1px solid transparent;
    font-family: '{FAMILY}'; font-size: 13px; font-weight: 600; }}
QPushButton[variant="primary"] {{ background: {sheen_qss()}; color: {ON_ACCENT}; }}
QPushButton[variant="primary"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[variant="primary"]:pressed {{ background: {ACCENT_TEXT}; }}
QPushButton[variant="danger"] {{ background: {DANGER_BG}; color: {DANGER_FG}; border-color: {DANGER_LINE}; }}
QPushButton[variant="danger"]:hover {{ background: #fbdcd8; }}
QPushButton[variant="secondary"] {{ background: {SURFACE}; color: {INK}; border-color: {LINE}; }}
QPushButton[variant="secondary"]:hover {{ border-color: {ACCENT}; color: {ACCENT_TEXT}; }}
QPushButton[variant="secondary"]:pressed {{ background: {SUNKEN}; }}
QPushButton[variant="ghost"] {{ background: transparent; color: {INK_2}; }}
QPushButton[variant="ghost"]:hover {{ background: {SUNKEN}; color: {INK}; }}
QPushButton[variant="ghost"]:checked {{ background: {ACCENT_SOFT}; color: {ACCENT_TEXT}; }}
QPushButton:disabled {{ background: transparent; color: {FAINT}; border-color: {LINE}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
"""
# Os mesmos botões sobre a pena (barras laterais e painéis escuros).
_BUTTONS_ON_PENA = f"""
QPushButton[variant="secondary"] {{ background: rgba(255,255,255,0.06); color: {ON_PENA};
    border-color: rgba(255,255,255,0.14); }}
QPushButton[variant="secondary"]:hover {{ background: rgba(255,255,255,0.11); border-color: {SIGNAL}; color: #ffffff; }}
QPushButton[variant="secondary"]:pressed {{ background: rgba(255,255,255,0.16); }}
QPushButton[variant="ghost"] {{ color: {ON_PENA_MUTED}; }}
QPushButton[variant="ghost"]:hover {{ background: rgba(255,255,255,0.08); color: {ON_PENA}; }}
QPushButton:focus {{ border-color: {SIGNAL}; }}
QPushButton:disabled {{ color: #5d6876; border-color: rgba(255,255,255,0.08); }}
"""
# Escolha única em segmentos (Segmented): a escolhida ganha o brilho da pena.
_DIAL = f"""
QFrame#dial {{ background: {SUNKEN}; border: none; border-radius: {RADIUS}px; }}
QFrame#dial QToolButton {{ color: {INK_2}; background: transparent; border: none; border-radius: 3px;
    padding: 5px 12px; font-family: '{DISPLAY}'; font-size: 13px; font-weight: 600; }}
QFrame#dial QToolButton:hover {{ color: {INK}; background: rgba(255,255,255,0.7); }}
QFrame#dial QToolButton:checked {{ background: {sheen_qss()}; color: {ON_ACCENT}; }}
"""
_DIAL_ON_PENA = f"""
QFrame#dial {{ background: rgba(255,255,255,0.07); }}
QFrame#dial QToolButton {{ color: {ON_PENA_MUTED}; }}
QFrame#dial QToolButton:hover {{ color: {ON_PENA}; background: rgba(255,255,255,0.08); }}
QFrame#dial QToolButton:checked {{ color: {ON_ACCENT}; }}
"""
_SCROLL = f"""
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE_STRONG}; border-radius: 2px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {LINE_STRONG}; border-radius: 2px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0;
    width: 0; }}
"""


def app_stylesheet() -> str:
    """Estilo global: tooltips, menus (bandeja e botão direito) e diálogos, todos na pena."""
    return f"""
QToolTip {{ background: {PENA}; color: {ON_PENA}; border: 1px solid {PENA_LINE}; padding: 5px 8px; border-radius: 3px;
    font-family: '{FAMILY}'; font-size: 12.5px; }}
QMenu {{ background: {PENA}; color: {ON_PENA}; border: 1px solid {PENA_LINE}; border-radius: {RADIUS}px; padding: 6px;
    font-family: '{FAMILY}'; font-size: 13.5px; min-width: 250px; }}
QMenu::item {{ padding: 8px 18px 8px 10px; border-radius: 3px; border-left: 2px solid transparent; }}
QMenu::item:selected {{ background: {PENA_3}; color: #ffffff; border-left: 2px solid {SIGNAL}; }}
QMenu::item:disabled {{ color: {ON_PENA_MUTED}; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::separator {{ height: 1px; background: {PENA_LINE}; margin: 5px 6px; }}
QMenu::right-arrow {{ width: 8px; }}
QDialog#klickDialog {{ background: {SURFACE}; }}
QDialog#klickDialog QLabel {{ color: {INK_2}; font-family: '{FAMILY}'; font-size: 13.5px; }}
QDialog#klickDialog QLabel#title {{ color: {INK}; }}
QFrame#dialogFoot {{ background: {PAGE}; border-top: 1px solid {LINE}; }}
QLabel#hint {{ color: {MUTED}; font-size: 11px; }}
{_BUTTONS}
"""


def panel_stylesheet() -> str:
    """Barras e painéis por cima da tela (captura, editar, gravar, aviso): vidro escuro da pena."""
    return f"""
QFrame#panel {{ background: transparent; border: none; }}
QToolButton {{ color: {ON_PENA}; background: transparent; border: 1px solid transparent; border-radius: 3px;
    padding: 6px; font-family: '{DISPLAY}'; }}
QToolButton:hover {{ background: rgba(255,255,255,0.09); color: #ffffff; }}
QToolButton:pressed {{ background: rgba(255,255,255,0.15); }}
QToolButton:checked {{ background: rgba(255,255,255,0.13); color: #ffffff; border-color: {SIGNAL}; }}
QToolButton:focus {{ border-color: {SIGNAL}; }}
QLabel {{ color: {ON_PENA}; }}
QFrame#divider {{ background: rgba(255,255,255,0.12); }}
QLabel[role="muted"] {{ color: {ON_PENA_MUTED}; }}
QLabel[role="section"] {{ color: {ON_PENA_MUTED}; font-family: '{DISPLAY}'; font-size: 13px; font-weight: 600; }}
{_DIAL}{_DIAL_ON_PENA}{_BUTTONS}{_BUTTONS_ON_PENA}
"""


def window_stylesheet() -> str:
    """Janelas (galeria, leitura, análise, configurações): conteúdo claro; o que tem objectName "pena" é escuro."""
    return f"""
QWidget#window {{ background: {PAGE}; color: {INK}; }}
QWidget#window QLabel {{ color: {INK}; }}
QWidget#window QLabel[role="muted"] {{ color: {MUTED}; }}
QWidget#window QLabel[role="section"] {{ color: {MUTED}; font-family: '{DISPLAY}'; font-size: 13px; font-weight: 600; }}
QWidget#pena {{ background: {PENA}; }}
QWidget#pena QLabel {{ color: {ON_PENA}; }}
QWidget#pena QLabel[role="muted"], QWidget#pena QLabel[role="section"] {{ color: {ON_PENA_MUTED}; }}
QLineEdit {{ background: {FIELD}; color: {INK}; border: 1px solid {LINE}; border-radius: {RADIUS}px;
    padding: 7px 12px; font-family: '{FAMILY}'; font-size: 13.5px; selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT_TEXT}; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QPlainTextEdit, QTextEdit {{ background: {FIELD}; color: {INK}; border: 1px solid {LINE}; border-radius: {RADIUS}px;
    padding: 8px; selection-background-color: {ACCENT_SOFT}; selection-color: {ACCENT_TEXT}; }}
QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {ACCENT}; }}
QListView, QScrollArea {{ background: transparent; border: none; }}
QComboBox {{ background: {FIELD}; color: {INK}; border: 1px solid {LINE}; border-radius: {RADIUS}px; padding: 6px 12px;
    min-width: 120px; }}
QComboBox QAbstractItemView {{ background: {FIELD}; color: {INK}; selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT_TEXT}; }}
{_SCROLL}{_DIAL}{_BUTTONS}
QWidget#pena QFrame#dial {{ background: rgba(255,255,255,0.07); }}
QWidget#pena QFrame#dial QToolButton {{ color: {ON_PENA_MUTED}; }}
QWidget#pena QFrame#dial QToolButton:checked {{ color: {ON_ACCENT}; }}
"""


def pena_buttons() -> str:
    """Folha para um widget de fundo escuro dentro de uma janela clara (os botões ficam claros sobre a pena)."""
    return _BUTTONS + _BUTTONS_ON_PENA
