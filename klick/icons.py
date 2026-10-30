"""Ícones em SVG (traço 1.8, pontas redondas), pintados na cor pedida."""

from __future__ import annotations

from functools import cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from klick import theme

_S = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"'
PATHS = {
    "copy": f'<rect x="8" y="8" width="12" height="12" rx="1.5" {_S}/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" {_S}/>',
    "read": f'<path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4" {_S}/><path d="M8.5 9h7M12 9v7" {_S}/>',
    "mark": f'<path d="m14 4 6 6-9 9H5v-6z" {_S} stroke-linejoin="round"/><path d="M4 21h16" {_S}/>',
    "save": f'<path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14" {_S}/>',
    "rec": f'<circle cx="12" cy="12" r="8" {_S}/><circle cx="12" cy="12" r="3.6" fill="currentColor"/>',
    "gif": f'<rect x="3" y="6" width="18" height="12" rx="1.5" {_S}/><path d="M9.5 10.5H8a1.5 1.5 0 0 0-1.5 1.5 1.5 1.5 0 0 0 1.5 1.5h1.5V12M12 10v4M14.5 14v-4h2.5M14.5 12h2" fill="none" stroke="currentColor" stroke-width="1.5"/>',
    "close": f'<path d="m7 7 10 10M17 7 7 17" {_S}/>',
    "search": f'<circle cx="11" cy="11" r="6" {_S}/><path d="m16 16 4 4" {_S}/>',
    "spot": f'<rect x="3" y="3" width="18" height="18" rx="1.5" fill="currentColor" opacity=".22"/><rect x="8" y="8" width="8" height="8" rx="1" {_S}/>',
    "arrow": f'<path d="M5 19 19 5m0 0h-7m7 0v7" {_S}/>',
    "step": f'<rect x="4" y="4" width="16" height="16" rx="2" {_S}/><path d="M10.5 9.5 12.5 8v8" {_S}/>',
    "loupe": f'<circle cx="10" cy="10" r="6" {_S}/><path d="m15 15 5 5M10 7.5v5M7.5 10h5" {_S}/>',
    "hide": '<path d="M4 4h5v5H4zM9 9h5v5H9zM14 4h5v5h-5zM4 14h5v5H4zM14 14h5v5h-5z" fill="currentColor"/>',
    "ruler": f'<rect x="2.5" y="8" width="19" height="8" rx="1" {_S}/><path d="M7 8v3M11 8v4M15 8v3M19 8v4" fill="none" stroke="currentColor" stroke-width="1.5"/>',
    "drop": f'<path d="m14 6 4 4M5 19l1-4 8.5-8.5a2 2 0 0 1 3 3L9 18z" {_S} stroke-linejoin="round"/>',
    "text": f'<path d="M6 6h12M12 6v13" {_S}/>',
    "image": f'<rect x="3" y="5" width="18" height="14" rx="1.5" {_S}/><path d="m3 16 5-5 4 4 3-3 6 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
    "video": f'<rect x="3" y="6" width="13" height="12" rx="1.5" {_S}/><path d="m16 10.5 5-3v9l-5-3" {_S} stroke-linejoin="round"/>',
    "clock": f'<circle cx="12" cy="12" r="8" {_S}/><path d="M12 8v4l3 2" {_S}/>',
    "power": f'<path d="M12 4v8M7.5 7a7 7 0 1 0 9 0" {_S}/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.4"/>',
    "trash": f'<path d="M5 7h14M10 7V4.5h4V7M7 7l1 13h8l1-13" {_S} stroke-linejoin="round"/>',
    "folder": f'<path d="M3.5 6.5v12h17V8.5H11L9 6H3.5z" {_S} stroke-linejoin="round"/>',
    "undo": f'<path d="M9 7 5 11l4 4" {_S}/><path d="M5 11h9a5 5 0 0 1 0 10h-3" {_S}/>',
    "warn": f'<path d="M12 4 21 19H3z" {_S} stroke-linejoin="round"/><path d="M12 10v4M12 16.5v.5" {_S}/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor"/>',
    "dot": '<circle cx="12" cy="12" r="5" fill="currentColor"/>',
    "lens": f'<path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M4 15v3.5A1.5 1.5 0 0 0 5.5 20H9" {_S}/><circle cx="12" cy="12" r="3.2" {_S}/><circle cx="18" cy="18" r="2" fill="currentColor"/>',
    "gear": ('<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0'
             '-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 '
             '2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 '
             '0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73'
             'l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73'
             'l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" '
             f'{_S} stroke-linejoin="round"/><circle cx="12" cy="12" r="3" {_S}/>'),
    "sql": f'<ellipse cx="12" cy="6" rx="7" ry="2.5" {_S}/><path d="M5 6v12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" {_S}/>',
    "table": f'<rect x="3" y="4.5" width="18" height="15" rx="1.5" {_S}/><path d="M3 9.5h18M3 14.5h18M9.5 4.5v15" {_S}/>',
    "globe": f'<circle cx="12" cy="12" r="8" {_S}/><path d="M4 12h16M12 4c2.5 2.5 2.5 13.5 0 16M12 4c-2.5 2.5-2.5 13.5 0 16" {_S}/>',
    "sound": f'<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z" {_S} stroke-linejoin="round"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" {_S}/>',
    "box": f'<rect x="4" y="6" width="16" height="12" rx="2" {_S}/>',
    "ellipse": f'<ellipse cx="12" cy="12" rx="8" ry="6" {_S}/>',
    "line": f'<path d="M5 19 19 5" {_S}/>',
    "pen": f'<path d="M3 15.5c2.2-3 4-3 5.5-.5s3.3 2.5 5.5-.5 3.6-3 7 0" {_S}/>',
    "blur": f'<circle cx="12" cy="12" r="7.5" {_S} stroke-dasharray="2.2 2.6"/><circle cx="12" cy="12" r="3" fill="currentColor" opacity=".35"/>',
    "keyboard": f'<rect x="2.5" y="6" width="19" height="12" rx="2" {_S}/><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M8 14h8" {_S}/>',
    "keep": f'<path d="M6.5 4h11v16.5L12 16.5l-5.5 4z" {_S}/>',
    "json": f'<path d="M9 4H8a2 2 0 0 0-2 2v3.5a2 2 0 0 1-2 2 2 2 0 0 1 2 2V18a2 2 0 0 0 2 2h1M15 4h1a2 2 0 0 1 2 2v3.5a2 2 0 0 0 2 2 2 2 0 0 0-2 2V18a2 2 0 0 1-2 2h-1" {_S}/>',
    "sum": f'<path d="M17 5H7l5.5 7L7 19h10" {_S}/>',
    "analysis": f'<path d="M4 20V10M10 20V4M16 20v-7M21 20H3" {_S}/>',

}


@cache
def pixmap(name: str, color: str = theme.A300, size: int = 18, ratio: float | None = None) -> QPixmap:
    if ratio is None:
        screen = QGuiApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen else 1.0
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{PATHS[name]}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.replace("currentColor", color).encode()))
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str = theme.A300, hover: str | None = None, checked: str | None = None,
         size: int = 18) -> QIcon:
    """Ícone com cor normal, ao passar o mouse (Active) e marcado (On)."""
    ico = QIcon()
    ico.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    ico.addPixmap(pixmap(name, hover or color, size), QIcon.Mode.Active, QIcon.State.Off)
    ico.addPixmap(pixmap(name, theme.G500, size), QIcon.Mode.Disabled, QIcon.State.Off)
    if checked:
        ico.addPixmap(pixmap(name, checked, size), QIcon.Mode.Normal, QIcon.State.On)
        ico.addPixmap(pixmap(name, checked, size), QIcon.Mode.Active, QIcon.State.On)
    return ico
