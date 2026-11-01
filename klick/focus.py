"""Foco no Windows para janelas abertas por atalho global (o painel de consultas, a captura).

O Klick ouve os atalhos com um gancho de teclado, que não dá direito de vir para a frente: sem ajuda, a
janela abre mas o foco fica no outro programa (o que você digita vai para lá). Para tomar o foco, a
thread do Klick se liga por um instante à fila de entrada do programa da frente.

Também acha onde está o cursor de texto do programa da frente (para o painel abrir ali, como o
Windows + V) e devolve o foco a ele colando com Ctrl+V.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor, QGuiApplication

log = logging.getLogger(__name__)


def foreground() -> int:
    """A janela que está na frente agora (0 fora do Windows)."""
    if sys.platform != "win32":
        return 0
    import ctypes

    return int(ctypes.windll.user32.GetForegroundWindow() or 0)


def take(widget) -> None:
    """Traz `widget` (uma janela de topo já visível) para a frente, com o foco do teclado."""
    widget.raise_()
    widget.activateWindow()
    if sys.platform != "win32":
        return
    import ctypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = int(widget.winId())
    front = user32.GetForegroundWindow()
    if front == hwnd:
        return
    theirs = user32.GetWindowThreadProcessId(front, None) if front else 0
    mine = kernel32.GetCurrentThreadId()
    attached = bool(theirs and theirs != mine and user32.AttachThreadInput(mine, theirs, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(mine, theirs, False)


def give_back(hwnd: int) -> None:
    """Devolve o foco à janela que estava na frente antes do Klick."""
    if sys.platform != "win32" or not hwnd:
        return
    import ctypes

    user32 = ctypes.windll.user32
    if user32.IsWindow(hwnd):
        user32.SetForegroundWindow(hwnd)


def paste() -> None:
    """Ctrl+V no programa da frente (o texto já deve estar no clipboard)."""
    try:
        from pynput.keyboard import Controller, Key
    except Exception:  # noqa: BLE001 - sem pynput, fica só no clipboard
        log.warning("Não foi possível colar sozinho", exc_info=True)
        return
    keyboard = Controller()
    with keyboard.pressed(Key.ctrl):
        keyboard.press("v")
        keyboard.release("v")


def caret_or_cursor() -> QPoint:
    """Onde abrir um painel: logo abaixo do cursor de texto do programa da frente, se ele disser onde está;
    senão, junto do mouse. Em coordenadas do Qt."""
    point = _caret()
    return point if point is not None else QCursor.pos()


def _caret() -> QPoint | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                    ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                    ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]

    user32 = ctypes.windll.user32
    front = user32.GetForegroundWindow()
    if not front:
        return None
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if not user32.GetGUIThreadInfo(user32.GetWindowThreadProcessId(front, None), ctypes.byref(info)):
        return None
    if not info.hwndCaret:
        return None  # o programa desenha o próprio cursor (navegadores, muitos editores): fica o mouse
    point = wintypes.POINT(info.rcCaret.left, info.rcCaret.bottom)
    if not user32.ClientToScreen(info.hwndCaret, ctypes.byref(point)):
        return None
    return _to_logical(point.x, point.y)


def _to_logical(x: int, y: int) -> QPoint | None:
    """Pixels do Windows -> coordenadas do Qt (cada monitor tem a sua escala; a origem fica em pixels)."""
    for screen in QGuiApplication.screens():
        geo, ratio = screen.geometry(), screen.devicePixelRatio()
        if geo.x() <= x < geo.x() + geo.width() * ratio and geo.y() <= y < geo.y() + geo.height() * ratio:
            return QPoint(round(geo.x() + (x - geo.x()) / ratio), round(geo.y() + (y - geo.y()) / ratio))
    return None
