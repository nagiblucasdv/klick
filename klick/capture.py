"""Captura de cada monitor em pixels físicos.

A tela inteira é congelada antes de abrir o overlay (como no Lightshot), então
o que o usuário vê enquanto seleciona é exatamente o que vai para o print.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QRect, QRectF, QSize
from PySide6.QtGui import QGuiApplication, QImage, QScreen

log = logging.getLogger(__name__)


@dataclass
class ScreenShot:
    screen: QScreen
    image: QImage  # pixels físicos do monitor


def _physical_rect(screen: QScreen) -> tuple[int, int, int, int]:
    geo = screen.geometry()
    dpr = screen.devicePixelRatio()
    return (
        round(geo.x() * dpr),
        round(geo.y() * dpr),
        round(geo.width() * dpr),
        round(geo.height() * dpr),
    )


def _grab_with_mss(screens: list[QScreen]) -> dict[QScreen, QImage]:
    import mss

    images: dict[QScreen, QImage] = {}
    with mss.mss() as sct:
        monitors = sct.monitors[1:]  # [0] é o desktop virtual inteiro
        for screen in screens:
            left, top, width, height = _physical_rect(screen)
            match = next(
                (m for m in monitors
                 if (m["left"], m["top"], m["width"], m["height"]) == (left, top, width, height)),
                None,
            )
            if match is None:
                continue
            shot = sct.grab(match)
            # BGRA em memória == QImage.Format_RGB32 em little-endian.
            image = QImage(shot.bgra, shot.width, shot.height, shot.width * 4, QImage.Format.Format_RGB32)
            images[screen] = image.copy()  # copy() desacopla do buffer do mss
    return images


def grab_screens() -> list[ScreenShot]:
    """Captura todos os monitores. Usa mss e cai para o Qt se não achar o monitor."""
    screens = QGuiApplication.screens()
    try:
        images = _grab_with_mss(screens)
    except Exception:  # noqa: BLE001 - mss indisponível (ex.: Wayland)
        log.warning("mss falhou, usando captura do Qt", exc_info=True)
        images = {}

    shots = []
    for screen in screens:
        image = images.get(screen)
        if image is None:
            image = screen.grabWindow(0).toImage()
        shots.append(ScreenShot(screen, image))
    return shots


def to_physical(selection: QRectF, logical_size: QSize, image_size: QSize) -> QRect:
    """Converte a seleção (coordenadas lógicas do widget) para pixels da imagem."""
    sx = image_size.width() / logical_size.width()
    sy = image_size.height() / logical_size.height()
    rect = QRect(
        round(selection.x() * sx),
        round(selection.y() * sy),
        round(selection.width() * sx),
        round(selection.height() * sy),
    )
    return rect.intersected(QRect(0, 0, image_size.width(), image_size.height()))
