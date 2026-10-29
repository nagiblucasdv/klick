"""Captura de cada monitor em pixels físicos.

A tela inteira é congelada antes de abrir o overlay (como no Lightshot), então
o que o usuário vê enquanto seleciona é exatamente o que vai para o print.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QRectF, QSize
from PySide6.QtGui import QGuiApplication, QImage, QScreen

log = logging.getLogger(__name__)


@dataclass
class ScreenShot:
    screen: QScreen
    image: QImage  # pixels físicos do monitor
    origin: QPoint  # canto do monitor no desktop virtual, em pixels físicos


@dataclass
class Selection:
    image: QImage  # recorte em pixels físicos
    rect: QRect  # área no desktop virtual, em pixels físicos (o que o ffmpeg usa)
    logical: QRect  # área em coordenadas lógicas globais do Qt (para posicionar janelas)
    screen: QScreen
    marked: bool = False  # a imagem já vem com as marcações feitas na própria captura
    quality: str = "medium"  # gravação: "low", "medium" ou "high"
    sound: str = "none"  # gravação: "none", "system", "mic" ou "both"

    @property
    def device_pixel_ratio(self) -> float:
        return self.rect.width() / self.logical.width() if self.logical.width() else 1.0


def _physical_rect(screen: QScreen) -> tuple[int, int, int, int]:
    geo = screen.geometry()
    dpr = screen.devicePixelRatio()
    return (
        round(geo.x() * dpr),
        round(geo.y() * dpr),
        round(geo.width() * dpr),
        round(geo.height() * dpr),
    )


def _grab_with_mss(screens: list[QScreen]) -> dict[QScreen, tuple[QImage, QPoint]]:
    import mss

    images: dict[QScreen, tuple[QImage, QPoint]] = {}
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
            images[screen] = (image.copy(), QPoint(match["left"], match["top"]))  # copy() desacopla do buffer
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
        if screen in images:
            image, origin = images[screen]
        else:
            left, top, _, _ = _physical_rect(screen)
            image, origin = screen.grabWindow(0).toImage(), QPoint(left, top)
        shots.append(ScreenShot(screen, image, origin))
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
