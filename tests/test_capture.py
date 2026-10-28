from datetime import datetime

from PySide6.QtCore import QRect, QRectF, QSize

from klick.capture import to_physical
from klick.config import default_filename


def test_to_physical_same_scale():
    assert to_physical(QRectF(10, 20, 30, 40), QSize(100, 100), QSize(100, 100)) == QRect(10, 20, 30, 40)


def test_to_physical_scales_for_high_dpi():
    # Monitor a 150%: 1280x720 lógicos == 1920x1080 físicos.
    rect = to_physical(QRectF(100, 100, 200, 50), QSize(1280, 720), QSize(1920, 1080))
    assert rect == QRect(150, 150, 300, 75)


def test_to_physical_clips_to_image():
    rect = to_physical(QRectF(90, 90, 50, 50), QSize(100, 100), QSize(100, 100))
    assert rect == QRect(90, 90, 10, 10)


def test_default_filename():
    assert default_filename(datetime(2026, 10, 28, 9, 5, 3)) == "klick_2026-10-28_09-05-03.png"
