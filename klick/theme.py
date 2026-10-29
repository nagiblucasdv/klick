"""Identidade Visor: cores, fontes e folhas de estilo do Klick.

Referência visual: grafite e alumínio no corpo, laranja de sinal só na ação principal,
medidas em fonte mono. Tudo o que fica por cima da tela (seleção, barras, menus, avisos,
HUD) é sempre grafite; as janelas (galeria, leitura) seguem o tema do Windows.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication

FONTS_DIR = Path(__file__).with_name("assets") / "fonts"
FAMILY = "Archivo"
MONO = "JetBrains Mono"

# Grafite: barras, menus, HUD e janelas no escuro.
G950, G900, G850, G800, G700, G600, G500, G400, G300 = (
    "#121110", "#1a1917", "#201f1c", "#272522", "#32302c", "#403d38", "#5c5851", "#7f7a71", "#a8a398")
# Alumínio: janelas no claro e texto sobre grafite.
A50, A100, A200, A300, A400 = "#f7f6f3", "#efede8", "#e3e0d9", "#d2cec5", "#b8b3a8"
PAPER = "#f2f0eb"
# Sinal: a cor da marca. 700 é para texto laranja sobre fundo claro.
S400, S500, S600, S700 = "#ff8a47", "#ff6a13", "#e85600", "#b64200"
# Estados: nunca se confundem com a marca.
OK, REC, WARN, CYAN = "#3ad07c", "#ff3b30", "#ffb020", "#3cc6f0"

DIM = QColor(18, 17, 16, 150)  # escurecimento fora da seleção


@dataclass(frozen=True)
class Scheme:
    """Cores de janela (galeria, leitura) num dos dois temas."""
    dark: bool
    bg: str
    surface: str
    field: str
    fg: str
    muted: str
    line: str
    accent_ink: str
    selected_bg: str
    selected_fg: str


LIGHT = Scheme(False, A100, A50, "#ffffff", G900, G500, A300, S700, G900, A50)
DARK = Scheme(True, G950, G900, G850, PAPER, G300, G700, S400, PAPER, G950)


def load_fonts() -> None:
    """Registra Archivo e JetBrains Mono (variáveis) que vão junto com o app."""
    if getattr(load_fonts, "done", False):
        return
    for name in ("Archivo.ttf", "JetBrainsMono.ttf"):
        QFontDatabase.addApplicationFont(str(FONTS_DIR / name))
    load_fonts.done = True


def font(px: float, weight: int = 500, width: int = 100, mono: bool = False) -> QFont:
    """Fonte do Visor em pixels. `width` é o eixo de largura da Archivo (88 barra, 100 interface, 125 títulos)."""
    load_fonts()
    f = QFont(MONO if mono else FAMILY)
    f.setPixelSize(round(px))
    f.setWeight(QFont.Weight(weight))
    if not mono:
        f.setVariableAxis(QFont.Tag("wdth"), float(width))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def window_scheme() -> Scheme:
    hints = QGuiApplication.styleHints()
    return DARK if hints.colorScheme() == Qt.ColorScheme.Dark else LIGHT


@cache
def _kbd_style() -> str:
    return (f"font-family:'{MONO}'; font-size:10px; color:{A200}; background:{G700};"
            " padding:0 4px; border-radius:2px;")


def tip(label: str, shortcut: str | None = None) -> str:
    """Texto de tooltip com o atalho em destaque, como no guia: "Ler o texto  Ctrl T"."""
    if not shortcut:
        return label
    return f"{label}&nbsp;&nbsp;<span style=\"{_kbd_style()}\">&nbsp;{shortcut}&nbsp;</span>"


# Botões: cara de tecla de câmera (borda inferior escura que some ao pressionar).
_BUTTONS = f"""
QPushButton {{ font-family: '{FAMILY}'; font-size: 13px; font-weight: 600; min-height: 30px; padding: 0 14px;
    border-radius: 3px; border: 1px solid transparent; }}
QPushButton[variant="primary"] {{ background: {S500}; color: {G950}; border-bottom: 2px solid #c94c00; }}
QPushButton[variant="primary"]:hover {{ background: {S400}; }}
QPushButton[variant="primary"]:pressed {{ background: {S600}; border-bottom-width: 1px; padding-top: 1px; }}
QPushButton[variant="danger"] {{ background: {REC}; color: #ffffff; border-bottom: 2px solid #b8231b; }}
QPushButton[variant="danger"]:hover {{ background: #ff5a50; }}
QPushButton[variant="danger"]:pressed {{ background: #e02b21; border-bottom-width: 1px; padding-top: 1px; }}
QPushButton:disabled {{ background: transparent; color: {G400}; border-color: {G700}; }}
"""

_DARK_BUTTONS = f"""
QPushButton[variant="secondary"] {{ background: {G700}; color: {PAPER}; border-color: {G600}; border-bottom-color: {G950}; }}
QPushButton[variant="secondary"]:hover {{ background: {G600}; }}
QPushButton[variant="secondary"]:pressed {{ background: {G800}; padding-top: 1px; }}
QPushButton[variant="ghost"] {{ background: transparent; color: {A300}; }}
QPushButton[variant="ghost"]:hover {{ background: rgba(255,255,255,0.07); color: {PAPER}; }}
QPushButton[variant="ghost"]:pressed {{ background: rgba(255,255,255,0.04); }}
QPushButton:focus {{ border-color: {S500}; }}
QPushButton[variant="primary"]:focus, QPushButton[variant="danger"]:focus {{ border-color: {A50}; }}
"""


def _light_buttons(s: Scheme) -> str:
    return f"""
QPushButton[variant="secondary"] {{ background: {s.surface}; color: {s.fg}; border-color: {s.line}; border-bottom-color: {A400}; }}
QPushButton[variant="secondary"]:hover {{ background: #ffffff; }}
QPushButton[variant="secondary"]:pressed {{ background: {A200}; padding-top: 1px; }}
QPushButton[variant="ghost"] {{ background: transparent; color: {G600}; }}
QPushButton[variant="ghost"]:hover {{ background: rgba(0,0,0,0.05); color: {G900}; }}
QPushButton:focus {{ border-color: {S500}; }}
QPushButton[variant="primary"]:focus {{ border-color: {G900}; }}
"""


def app_stylesheet() -> str:
    """Estilo global: tooltips, menus (bandeja e botão direito) e diálogos são sempre grafite."""
    return f"""
QToolTip {{ background: {G950}; color: {PAPER}; border: 1px solid {G700}; padding: 4px 7px; border-radius: 3px;
    font-family: '{FAMILY}'; font-size: 12px; }}
QMenu {{ background: {G900}; color: {PAPER}; border: 1px solid {G700}; border-radius: 4px; padding: 5px;
    font-family: '{FAMILY}'; font-size: 13px; min-width: 250px; }}
QMenu::item {{ padding: 7px 18px 7px 10px; border-radius: 3px; }}
QMenu::item:selected {{ background: {G700}; }}
QMenu::item:disabled {{ color: {G500}; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::separator {{ height: 1px; background: {G700}; margin: 5px 4px; }}
QMenu::right-arrow {{ width: 8px; }}
QDialog#klickDialog {{ background: {G900}; }}
QDialog#klickDialog QLabel {{ color: {A300}; font-family: '{FAMILY}'; font-size: 13px; }}
QDialog#klickDialog QLabel#title {{ color: {PAPER}; }}
QFrame#dialogFoot {{ background: {G850}; border-top: 1px solid {G700}; }}
QLabel#hint {{ color: {G400}; font-size: 11px; }}
{_BUTTONS}{_DARK_BUTTONS}
"""


def dark_panel_stylesheet() -> str:
    """Barras e HUD que ficam por cima da tela."""
    return f"""
QFrame#panel {{ background: {G900}; border: 1px solid {G700}; border-radius: 4px; }}
QToolButton {{ color: {A300}; background: transparent; border: none; border-radius: 3px; padding: 6px; }}
QToolButton:hover {{ background: {G700}; color: #ffffff; }}
QToolButton:pressed {{ background: {G800}; }}
QToolButton:checked {{ background: {S500}; color: {G950}; }}
QToolButton:focus {{ border: 1px solid {S500}; }}
QLabel {{ color: {PAPER}; }}
QFrame#divider {{ background: {G700}; }}
{_BUTTONS}{_DARK_BUTTONS}
"""


def window_stylesheet(s: Scheme) -> str:
    """Janelas (galeria, leitura) no tema do Windows."""
    buttons = _DARK_BUTTONS if s.dark else _light_buttons(s)
    scroll_handle = G600 if s.dark else A400
    return f"""
QWidget#window {{ background: {s.bg}; color: {s.fg}; }}
QWidget#window QLabel {{ color: {s.fg}; }}
QWidget#window QLabel[role="muted"] {{ color: {s.muted}; }}
QLineEdit {{ background: {s.field}; color: {s.fg}; border: 1px solid {s.line}; border-radius: 3px; padding: 6px 10px;
    font-family: '{FAMILY}'; font-size: 13px; selection-background-color: {S500}; selection-color: {G950}; }}
QLineEdit:focus {{ border-color: {S500}; }}
QListView, QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {scroll_handle}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
QFrame#dial {{ background: {s.surface}; border: 1px solid {s.line}; border-radius: 4px; }}
QFrame#dial QToolButton {{ color: {s.muted}; background: transparent; border: none; border-radius: 3px;
    padding: 6px 12px; font-family: '{FAMILY}'; font-size: 13px; font-weight: 600; }}
QFrame#dial QToolButton:hover {{ color: {s.fg}; }}
QFrame#dial QToolButton:checked {{ background: {s.selected_bg}; color: {s.selected_fg}; }}
{_BUTTONS}{buttons}
"""
