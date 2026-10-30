"""Ícone do app: o selo com a cabeça do corvo, cujo olho é a mira de captura.

Fica em SVG no próprio código (sem arquivo). Em 16 e 24 px usa um desenho mais simples,
sem os traços da mira e o reflexo, para não virar borrão na bandeja.
"""

from __future__ import annotations

from functools import cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_DEFS = """<defs>
<radialGradient id="disc" cx="0.35" cy="0.28" r="0.85"><stop offset="0" stop-color="#46D6C4"/>
<stop offset="0.6" stop-color="#0E7C70"/><stop offset="1" stop-color="#05332E"/></radialGradient>
<linearGradient id="head" x1="0" y1="0" x2="0.3" y2="1"><stop offset="0" stop-color="#2E2A26"/>
<stop offset="1" stop-color="#0D0C0A"/></linearGradient>
</defs>"""
_HEAD = ('<path d="M14.8 56.6 C10.5 44 14 31 24 22.5 C31 18 40 17 45.5 20.5 C47.5 21.7 49 23 50 24.5 L46.5 35 '
         'C46 40 43 44 39.5 46.5 L42 50.5 L36.5 50 L37.5 54.5 L33.5 54 L37.2 61.5 A30 30 0 0 1 14.8 56.6 Z" '
         'fill="url(#head)"/>'
         '<path d="M45.5 20.2 C52 21 58 24.5 62.5 29.5 L46.5 35 Z" fill="#4A443D"/>'
         '<path d="M50 24.5 L62.5 29.5 L46.5 35 Z" fill="#1E1B18" fill-opacity=".45"/>')

FULL = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{_DEFS}
<circle cx="32" cy="32" r="30" fill="url(#disc)"/>{_HEAD}
<circle cx="38" cy="27.5" r="4.4" fill="none" stroke="#7BE6D7" stroke-width="1.5"/>
<path d="M38 21.4 v2.4 M38 31.2 v2.4 M31.9 27.5 h2.4 M41.7 27.5 h2.4" stroke="#7BE6D7" stroke-width="1.5"
 stroke-linecap="round"/>
<circle cx="38" cy="27.5" r="1.5" fill="#fff"/>
<path d="M17 13.5 C23.5 7 35 5.5 44 9.5" stroke="#fff" stroke-opacity=".45" stroke-width="2.4" fill="none"
 stroke-linecap="round"/>
</svg>"""

SMALL = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{_DEFS}
<circle cx="32" cy="32" r="31" fill="url(#disc)"/>{_HEAD}
<circle cx="38" cy="27.5" r="5" fill="#7BE6D7"/><circle cx="38" cy="27.5" r="2.4" fill="#fff"/>
</svg>"""

SIZES = (16, 24, 32, 48, 64, 128, 256)


@cache
def app_icon() -> QIcon:
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(_draw(size))
    return icon


def _draw(size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray((SMALL if size <= 24 else FULL).encode()))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return pixmap
