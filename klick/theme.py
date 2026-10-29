"""Identidade Painel: cores, fontes e folhas de estilo do Klick.

Estrutura do Windows 11 (barra lateral como no Explorador, cantos de 8 px nas janelas)
com os instrumentos de um painel: aço azulado no corpo, laranja de sinal só nas ações,
leituras (tamanho, hora, fps, contagens) em ciano e fonte mono. Botões em caixa alta.
Tudo é escuro, por cima da tela e nas janelas.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase

FONTS_DIR = Path(__file__).with_name("assets") / "fonts"
FAMILY = "Barlow"
DISPLAY = "Barlow Condensed"  # títulos e rótulos estreitos
MONO = "JetBrains Mono"

# Aço: fundos, painéis, linhas e texto apagado (os nomes G* vêm da identidade anterior).
G950, G900, G850, G800, G700, G600, G500, G400, G300 = (
    "#0b1216", "#111b21", "#142027", "#18252d", "#24363f", "#2f4651", "#4f6672", "#7d929c", "#a9bcc4")
# Claros: texto sobre o aço.
A50, A100, A200, A300, A400 = "#f1f6f8", "#d8e4ea", "#c3d2d9", "#a9bcc4", "#8fa3ad"
PAPER = "#e6eef2"
# Sinal: a cor das ações. 700 é para texto laranja sobre fundo claro.
S400, S500, S600, S700 = "#ff8a47", "#ff6a13", "#e85600", "#b64200"
# Estados e leituras: nunca se confundem com a ação.
OK, REC, WARN, CYAN = "#3ad07c", "#ff3b30", "#ffb020", "#3cc6f0"
DATA = "#5fd3f5"  # números e medidas
DANGER_BG, DANGER_FG, DANGER_LINE = "#3a1214", "#ff6b6b", "#6b2023"

RADIUS = 3  # controles (botões, campos)
WINDOW_RADIUS = 6  # cartões e painéis

DIM = QColor(11, 18, 22, 150)  # escurecimento fora da seleção


@dataclass(frozen=True)
class Scheme:
    """Cores das janelas (galeria, leitura, configurações)."""
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


DARK = Scheme(True, G950, G900, G850, PAPER, G400, G700, S400, G700, DATA)
LIGHT = DARK  # o Painel é sempre escuro; o nome fica para quem ainda importa


def load_fonts() -> None:
    """Registra Barlow, Barlow Condensed e JetBrains Mono, que vão junto com o app."""
    if getattr(load_fonts, "done", False):
        return
    for path in sorted(FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(path))
    load_fonts.done = True


def font(px: float, weight: int = 500, width: int = 100, mono: bool = False, caps: bool = False) -> QFont:
    """Fonte do Painel em pixels. `width` acima de 100 usa a Barlow Condensed (títulos); `caps` deixa em
    caixa alta com espaçamento, como nos botões."""
    load_fonts()
    family = MONO if mono else (DISPLAY if width > 100 else FAMILY)
    f = QFont(family)
    f.setPixelSize(round(px))
    f.setWeight(QFont.Weight(weight))
    if caps:
        f.setCapitalization(QFont.Capitalization.AllUppercase)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.9)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def window_scheme() -> Scheme:
    return DARK


@cache
def _kbd_style() -> str:
    return (f"font-family:'{MONO}'; font-size:10px; color:{DATA}; background:{G800};"
            f" padding:0 4px; border-radius:2px;")


def tip(label: str, shortcut: str | None = None) -> str:
    """Texto de tooltip com o atalho em destaque, como no guia: "Ler o texto  Ctrl T"."""
    if not shortcut:
        return label
    return f"{label}&nbsp;&nbsp;<span style=\"{_kbd_style()}\">&nbsp;{shortcut}&nbsp;</span>"


# Botões de painel: retos, caixa alta (pela fonte, ver widgets.button), laranja só na ação.
_BUTTONS = f"""
QPushButton {{ min-height: 30px; padding: 0 14px; border-radius: {RADIUS}px; border: 1px solid transparent; }}
QPushButton[variant="primary"] {{ background: {S500}; color: {G950}; }}
QPushButton[variant="primary"]:hover {{ background: {S400}; }}
QPushButton[variant="primary"]:pressed {{ background: {S600}; padding-top: 1px; }}
QPushButton[variant="danger"] {{ background: {DANGER_BG}; color: {DANGER_FG}; border-color: {DANGER_LINE}; }}
QPushButton[variant="danger"]:hover {{ background: #4a171a; }}
QPushButton[variant="danger"]:pressed {{ background: #2d0e10; padding-top: 1px; }}
QPushButton[variant="secondary"] {{ background: {G800}; color: {PAPER}; border-color: {G700}; }}
QPushButton[variant="secondary"]:hover {{ background: {G700}; }}
QPushButton[variant="secondary"]:pressed {{ background: {G850}; padding-top: 1px; }}
QPushButton[variant="ghost"] {{ background: transparent; color: {A300}; }}
QPushButton[variant="ghost"]:hover {{ background: {G800}; color: {PAPER}; }}
QPushButton[variant="ghost"]:pressed {{ background: {G850}; }}
QPushButton[variant="ghost"]:checked {{ background: {G700}; color: {DATA}; border-bottom: 2px solid {CYAN}; }}
QPushButton:disabled {{ background: transparent; color: {G500}; border-color: {G700}; }}
QPushButton:focus {{ border-color: {CYAN}; }}
"""
# Abas e escolhas (Segmented): a escolhida ganha a linha ciano embaixo.
_DIAL = f"""
QFrame#dial {{ background: {G950}; border: 1px solid {G700}; border-radius: {RADIUS + 1}px; }}
QFrame#dial QToolButton {{ color: {A400}; background: transparent; border: none; border-radius: {RADIUS}px;
    padding: 5px 10px; font-family: '{FAMILY}'; font-size: 12.5px; font-weight: 600; }}
QFrame#dial QToolButton:hover {{ color: {PAPER}; background: {G800}; }}
QFrame#dial QToolButton:checked {{ background: {G700}; color: {DATA}; border-bottom: 2px solid {CYAN}; }}
"""


def app_stylesheet() -> str:
    """Estilo global: tooltips, menus (bandeja e botão direito) e diálogos."""
    return f"""
QToolTip {{ background: {G800}; color: {PAPER}; border: 1px solid {G700}; padding: 4px 7px; border-radius: {RADIUS}px;
    font-family: '{FAMILY}'; font-size: 12.5px; }}
QMenu {{ background: {G900}; color: {PAPER}; border: 1px solid {G700}; border-radius: {WINDOW_RADIUS}px; padding: 5px;
    font-family: '{FAMILY}'; font-size: 13.5px; min-width: 250px; }}
QMenu::item {{ padding: 7px 18px 7px 10px; border-radius: {RADIUS}px; }}
QMenu::item:selected {{ background: {G700}; }}
QMenu::item:disabled {{ color: {G500}; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::separator {{ height: 1px; background: {G700}; margin: 5px 4px; }}
QMenu::right-arrow {{ width: 8px; }}
QDialog#klickDialog {{ background: {G900}; }}
QDialog#klickDialog QLabel {{ color: {A300}; font-family: '{FAMILY}'; font-size: 13.5px; }}
QDialog#klickDialog QLabel#title {{ color: {PAPER}; }}
QFrame#dialogFoot {{ background: {G850}; border-top: 1px solid {G700}; }}
QLabel#hint {{ color: {G400}; font-size: 11px; }}
{_BUTTONS}
"""


def dark_panel_stylesheet() -> str:
    """Barras e HUD que ficam por cima da tela."""
    return f"""
QFrame#panel {{ background: {G900}; border: 1px solid {G700}; border-radius: {WINDOW_RADIUS}px; }}
QToolButton {{ color: {A300}; background: transparent; border: none; border-radius: {RADIUS}px; padding: 6px; }}
QToolButton:hover {{ background: {G700}; color: #ffffff; }}
QToolButton:pressed {{ background: {G800}; }}
QToolButton:checked {{ background: {G700}; color: {DATA}; }}
QToolButton:focus {{ border: 1px solid {CYAN}; }}
QLabel {{ color: {PAPER}; }}
QFrame#divider {{ background: {G700}; }}
QLabel[role="muted"] {{ color: {G400}; }}
QLabel[role="section"] {{ color: {G400}; font-family: '{MONO}'; font-size: 10.5px; letter-spacing: 1px; }}
{_DIAL}{_BUTTONS}
"""


def window_stylesheet(s: Scheme = DARK) -> str:
    """Janelas (galeria, leitura, configurações)."""
    return f"""
QWidget#window {{ background: {s.bg}; color: {s.fg}; }}
QWidget#window QLabel {{ color: {s.fg}; }}
QWidget#window QLabel[role="muted"] {{ color: {s.muted}; }}
QWidget#window QLabel[role="data"] {{ color: {DATA}; }}
QLineEdit {{ background: {s.field}; color: {s.fg}; border: 1px solid {s.line}; border-radius: {RADIUS}px; padding: 6px 10px;
    font-family: '{FAMILY}'; font-size: 13.5px; selection-background-color: {S500}; selection-color: {G950}; }}
QLineEdit:focus {{ border-color: {CYAN}; }}
QListView, QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {G600}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
{_DIAL}{_BUTTONS}
"""
