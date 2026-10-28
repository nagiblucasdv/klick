from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtTest import QTest

from klick.actions import Action
from klick.capture import ScreenShot
from klick.overlay import CaptureSession, SelectionOverlay


def make_shot(scale: int = 1) -> tuple[ScreenShot, QImage]:
    screen = QGuiApplication.primaryScreen()
    geo = screen.geometry()
    image = QImage(geo.width() * scale, geo.height() * scale, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    # Um bloco vermelho para conferir que o recorte pega o lugar certo.
    for x in range(20 * scale, 40 * scale):
        for y in range(20 * scale, 40 * scale):
            image.setPixelColor(x, y, QColor("red"))
    return ScreenShot(screen, image), image


def drag(widget, start: QPoint, end: QPoint) -> None:
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(widget, end)
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)


def test_drag_creates_selection_and_shows_toolbar(qapp):
    shot, _ = make_shot()
    overlay = SelectionOverlay(shot)
    overlay.show()
    drag(overlay, QPoint(60, 50), QPoint(10, 10))  # arrastar ao contrário também vale
    assert overlay.selection == QRectF(10, 10, 50, 40)
    assert overlay._toolbar.isVisible()
    overlay.close()


def test_click_without_drag_is_not_a_selection(qapp):
    shot, _ = make_shot()
    overlay = SelectionOverlay(shot)
    overlay.show()
    drag(overlay, QPoint(30, 30), QPoint(31, 31))
    assert not overlay._toolbar.isVisible()
    overlay.close()


def test_crop_uses_physical_pixels(qapp):
    shot, _ = make_shot(scale=2)
    overlay = SelectionOverlay(shot)
    overlay.show()
    drag(overlay, QPoint(20, 20), QPoint(40, 40))
    crop = overlay.cropped()
    assert (crop.width(), crop.height()) == (40, 40)
    assert crop.pixelColor(0, 0) == QColor("red")
    overlay.close()


def test_direct_action_finishes_on_release(qapp):
    shot, _ = make_shot()
    session = CaptureSession([shot], direct_action=Action.COPY)
    results = []
    session.finished.connect(lambda action, image: results.append((action, image.size())))
    session.start()
    drag(session.overlays[0], QPoint(10, 10), QPoint(30, 20))
    assert results == [(Action.COPY, results[0][1])]
    assert (results[0][1].width(), results[0][1].height()) == (20, 10)


def test_escape_cancels_session(qapp):
    shot, _ = make_shot()
    session = CaptureSession([shot])
    cancelled = []
    session.cancelled.connect(lambda: cancelled.append(True))
    session.start()
    QTest.keyClick(session.overlays[0], Qt.Key.Key_Escape)
    assert cancelled == [True]


def test_ctrl_c_copies_selection(qapp):
    shot, _ = make_shot()
    session = CaptureSession([shot])
    actions = []
    session.finished.connect(lambda action, image: actions.append(action))
    session.start()
    overlay = session.overlays[0]
    drag(overlay, QPoint(10, 10), QPoint(50, 50))
    QTest.keyClick(overlay, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert actions == [Action.COPY]
