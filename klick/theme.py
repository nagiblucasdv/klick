"""Identidade Névoa: cores, fontes e folhas de estilo do Klick.

Vidro claro sobre areia: superfícies quase brancas e translúcidas, verde-petróleo só nas
ações, vermelho só para gravar, âmbar para o que é temporário. Uma família só (Manrope),
com a hierarquia feita pelo peso; números e atalhos em JetBrains Mono. Cantos bem
arredondados e botões em pílula.

Os nomes das cores (G*, A*, S*) vêm das identidades anteriores e foram mantidos para o
resto do código: G* são as superfícies e linhas, A300 e PAPER o texto, S* a ação.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette

FONTS_DIR = Path(__file__).with_name("assets") / "fonts"
FAMILY = "Manrope"
MONO = "JetBrains Mono"

# Superfícies e linhas, da página (950) à linha mais forte (600); 500 e 400 são textos apagados.
G950, G900, G850, G800, G700, G600, G500, G400 = (
    "#f3f0eb", "#fbf9f6", "#ffffff", "#efeae3", "#e2dbd0", "#cfc6b9", "#8f867b", "#5a534b")
A300 = "#4a443d"  # texto de ícones e botões
PAPER = "#1e1b18"  # texto principal
# Ação (verde-petróleo): 600 é o tom para texto; SOFT é o fundo do que está escolhido.
S400, S500, S600 = "#139482", "#0e7c70", "#0b6359"
SOFT = "#ddf1ee"
# Estados: gravar, ok, aviso e o selo do que é temporário.
OK, REC, WARN = "#1f8a5b", "#c2412d", "#9a5b00"
DATA = S600  # números e medidas
TEMP_FG, TEMP_BG = "#7a4a00", "#fbefd9"
DANGER_BG, DANGER_FG, DANGER_LINE = "#fdecea", "#b42318", "#f4c7c1"
INK = "#ffffff"  # texto sobre a cor de ação

GLASS = QColor(255, 253, 250, 214)  # painéis sobre a tela congelada (com o fundo desfocado por baixo)
GLASS_LINE = QColor(255, 255, 255, 235)

RADIUS = 9  # controles (campos, botões quadrados)
PILL = 17  # botões em pílula de 34 px
WINDOW_RADIUS = 14  # cartões e painéis

DIM = QColor(30, 27, 24, 110)  # escurecimento fora da seleção


@dataclass(frozen=True)
class Scheme:
    """Cores das janelas (galeria, leitura, análise, configurações)."""
    bg: str
    surface: str
    field: str
    fg: str
    muted: str
    line: str


LIGHT = Scheme(G950, G900, G850, PAPER, G400, G700)


def apply(app: QGuiApplication) -> None:
    """Fontes, esquema claro (mesmo com o Windows no modo escuro) e a paleta da Névoa no app todo."""
    load_fonts()
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, G950), (QPalette.ColorRole.Base, G850),
                        (QPalette.ColorRole.AlternateBase, G900), (QPalette.ColorRole.Button, G900),
                        (QPalette.ColorRole.WindowText, PAPER), (QPalette.ColorRole.Text, PAPER),
                        (QPalette.ColorRole.ButtonText, PAPER), (QPalette.ColorRole.PlaceholderText, G500),
                        (QPalette.ColorRole.Highlight, SOFT), (QPalette.ColorRole.HighlightedText, S600),
                        (QPalette.ColorRole.ToolTipBase, G900), (QPalette.ColorRole.ToolTipText, PAPER),
                        (QPalette.ColorRole.Link, S600), (QPalette.ColorRole.Mid, G600),
                        (QPalette.ColorRole.Midlight, G700), (QPalette.ColorRole.Light, G850)):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setFont(font(13))
    app.setStyleSheet(app_stylesheet())


def load_fonts() -> None:
    """Registra Manrope e JetBrains Mono, que vão junto com o app."""
    if getattr(load_fonts, "done", False):
        return
    for path in sorted(FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(path))
    load_fonts.done = True


def font(px: float, weight: int = 500, width: int = 100, mono: bool = False, caps: bool = False) -> QFont:
    """Fonte em pixels. `width` acima de 100 (títulos) só reforça o peso; `caps` é para rótulos de seção."""
    load_fonts()
    f = QFont(MONO if mono else FAMILY)
    f.setPixelSize(round(px))
    if width > 100 and not mono:
        weight = max(weight, 700)
    f.setWeight(QFont.Weight(min(weight, 800)))
    if caps:
        f.setCapitalization(QFont.Capitalization.AllUppercase)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.7)
    if mono:  # sem ligaduras: ">=" continua ">=" e não vira "≥" (pareceria que o OCR mudou o texto)
        for tag in ("calt", "liga"):
            f.setFeature(QFont.Tag(tag), 0)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def window_scheme() -> Scheme:
    return LIGHT


@cache
def _kbd_style() -> str:
    return (f"font-family:'{MONO}'; font-size:10px; color:{A300}; background:{G800};"
            f" padding:0 4px; border-radius:4px;")


def tip(label: str, shortcut: str | None = None) -> str:
    """Texto de tooltip com o atalho em destaque: "Ler o texto  Ctrl T"."""
    if not shortcut:
        return label
    return f"{label}&nbsp;&nbsp;<span style=\"{_kbd_style()}\">&nbsp;{shortcut}&nbsp;</span>"


# Botões em pílula: verde só na ação principal (uma por tela).
_BUTTONS = f"""
QPushButton {{ min-height: 34px; padding: 0 16px; border-radius: {PILL}px; border: 1px solid transparent;
    font-family: '{FAMILY}'; font-size: 13px; font-weight: 700; }}
QPushButton[variant="primary"] {{ background: {S500}; color: {INK}; }}
QPushButton[variant="primary"]:hover {{ background: {S400}; }}
QPushButton[variant="primary"]:pressed {{ background: {S600}; }}
QPushButton[variant="danger"] {{ background: {DANGER_BG}; color: {DANGER_FG}; border-color: {DANGER_LINE}; }}
QPushButton[variant="danger"]:hover {{ background: #fbdcd8; }}
QPushButton[variant="secondary"] {{ background: rgba(255,255,255,0.78); color: {PAPER}; border-color: {G700}; }}
QPushButton[variant="secondary"]:hover {{ background: #ffffff; border-color: {G600}; }}
QPushButton[variant="secondary"]:pressed {{ background: {G800}; }}
QPushButton[variant="ghost"] {{ background: transparent; color: {A300}; }}
QPushButton[variant="ghost"]:hover {{ background: rgba(30,27,24,0.06); color: {PAPER}; }}
QPushButton[variant="ghost"]:pressed {{ background: rgba(30,27,24,0.10); }}
QPushButton[variant="ghost"]:checked {{ background: {SOFT}; color: {S600}; }}
QPushButton:disabled {{ background: transparent; color: {G500}; border-color: {G700}; }}
QPushButton:focus {{ border-color: {S500}; }}
"""
# Abas e escolhas (Segmented): trilho cinza-areia, a escolhida vira uma pílula branca.
_DIAL = f"""
QFrame#dial {{ background: rgba(30,27,24,0.06); border: none; border-radius: {PILL}px; }}
QFrame#dial QToolButton {{ color: {A300}; background: transparent; border: none; border-radius: 14px;
    padding: 6px 13px; font-family: '{FAMILY}'; font-size: 12.5px; font-weight: 600; }}
QFrame#dial QToolButton:hover {{ color: {PAPER}; background: rgba(255,255,255,0.55); }}
QFrame#dial QToolButton:checked {{ background: #ffffff; color: {S600}; font-weight: 700; }}
"""


def app_stylesheet() -> str:
    """Estilo global: tooltips, menus (bandeja e botão direito) e diálogos."""
    return f"""
QToolTip {{ background: {G900}; color: {PAPER}; border: 1px solid {G700}; padding: 5px 8px; border-radius: 8px;
    font-family: '{FAMILY}'; font-size: 12.5px; }}
QMenu {{ background: {G900}; color: {PAPER}; border: 1px solid {G700}; border-radius: {WINDOW_RADIUS}px; padding: 6px;
    font-family: '{FAMILY}'; font-size: 13.5px; font-weight: 500; min-width: 250px; }}
QMenu::item {{ padding: 8px 18px 8px 10px; border-radius: 9px; }}
QMenu::item:selected {{ background: {SOFT}; color: {S600}; }}
QMenu::item:disabled {{ color: {G500}; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::separator {{ height: 1px; background: {G700}; margin: 5px 6px; }}
QMenu::right-arrow {{ width: 8px; }}
QDialog#klickDialog {{ background: {G900}; }}
QDialog#klickDialog QLabel {{ color: {A300}; font-family: '{FAMILY}'; font-size: 13.5px; }}
QDialog#klickDialog QLabel#title {{ color: {PAPER}; }}
QFrame#dialogFoot {{ background: {G950}; border-top: 1px solid {G700}; }}
QLabel#hint {{ color: {G400}; font-size: 11px; }}
{_BUTTONS}
"""


def dark_panel_stylesheet() -> str:
    """Barras e painéis que ficam por cima da tela (o nome vem de quando eram escuros)."""
    return f"""
QFrame#panel {{ background: transparent; border: none; }}
QToolButton {{ color: {A300}; background: transparent; border: none; border-radius: 12px; padding: 6px; }}
QToolButton:hover {{ background: rgba(255,255,255,0.85); color: {PAPER}; }}
QToolButton:pressed {{ background: {G800}; }}
QToolButton:checked {{ background: #ffffff; color: {S600}; }}
QToolButton:focus {{ border: 1px solid {S500}; }}
QLabel {{ color: {PAPER}; }}
QFrame#divider {{ background: rgba(30,27,24,0.12); }}
QLabel[role="muted"] {{ color: {G400}; }}
QLabel[role="section"] {{ color: {G400}; font-family: '{FAMILY}'; font-size: 10.5px; font-weight: 700;
    letter-spacing: 0.8px; }}
{_DIAL}{_BUTTONS}
"""


def window_stylesheet(s: Scheme = LIGHT) -> str:
    """Janelas (galeria, leitura, análise, configurações)."""
    return f"""
QWidget#window {{ background: {s.bg}; color: {s.fg}; }}
QWidget#window QLabel {{ color: {s.fg}; }}
QWidget#window QLabel[role="muted"] {{ color: {s.muted}; }}
QWidget#window QLabel[role="data"] {{ color: {DATA}; }}
QWidget#window QLabel[role="section"] {{ color: {s.muted}; }}
QLineEdit {{ background: {s.field}; color: {s.fg}; border: 1px solid {s.line}; border-radius: {RADIUS}px;
    padding: 7px 12px; font-family: '{FAMILY}'; font-size: 13.5px; selection-background-color: {SOFT};
    selection-color: {S600}; }}
QLineEdit:focus {{ border: 1px solid {S500}; }}
QListView, QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {G600}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {G600}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; width: 0; }}
{_DIAL}{_BUTTONS}
"""
