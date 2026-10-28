from PySide6.QtCore import QPoint, QRect, QRectF, Qt
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
    return ScreenShot(screen, image, QPoint(100 * scale, 0)), image


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
    session.finished.connect(lambda action, selection: results.append((action, selection)))
    session.start()
    drag(session.overlays[0], QPoint(10, 10), QPoint(30, 20))
    [(action, selection)] = results
    assert action is Action.COPY
    assert (selection.image.width(), selection.image.height()) == (20, 10)
    assert selection.rect == QRect(110, 10, 20, 10)  # deslocado pela origem física do monitor


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
    session.finished.connect(lambda action, selection: actions.append(action))
    session.start()
    overlay = session.overlays[0]
    drag(overlay, QPoint(10, 10), QPoint(50, 50))
    QTest.keyClick(overlay, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert actions == [Action.COPY]


def test_selection_rect_is_physical_on_high_dpi(qapp):
    shot, _ = make_shot(scale=2)
    overlay = SelectionOverlay(shot)
    overlay.show()
    drag(overlay, QPoint(20, 20), QPoint(40, 50))
    selection = overlay.current()
    assert selection.rect == QRect(240, 40, 40, 60)
    assert selection.logical.size() == QRect(0, 0, 20, 30).size()
    assert selection.device_pixel_ratio == 2
    overlay.close()


def test_ctrl_keys_map_to_actions(qapp):
    for key, expected in ((Qt.Key.Key_E, Action.EDIT), (Qt.Key.Key_R, Action.RECORD), (Qt.Key.Key_G, Action.GIF)):
        shot, _ = make_shot()
        session = CaptureSession([shot])
        actions = []
        session.finished.connect(lambda action, selection: actions.append(action))
        session.start()
        overlay = session.overlays[0]
        drag(overlay, QPoint(10, 10), QPoint(50, 50))
        QTest.keyClick(overlay, key, Qt.KeyboardModifier.ControlModifier)
        assert actions == [expected]
