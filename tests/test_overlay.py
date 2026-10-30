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
    for key, expected in ((Qt.Key.Key_T, Action.READ), (Qt.Key.Key_L, Action.LENS), (Qt.Key.Key_Q, Action.SQL)):
        shot, _ = make_shot()
        session = CaptureSession([shot])
        actions = []
        session.finished.connect(lambda action, selection: actions.append(action))
        session.start()
        overlay = session.overlays[0]
        drag(overlay, QPoint(10, 10), QPoint(50, 50))
        QTest.keyClick(overlay, key, Qt.KeyboardModifier.ControlModifier)
        assert actions == [expected]


def test_print_mode_has_no_recording(qapp):
    shot, _ = make_shot()
    overlay = SelectionOverlay(shot)
    overlay.show()
    drag(overlay, QPoint(10, 10), QPoint(50, 50))
    assert Action.RECORD not in overlay._toolbar.buttons and Action.GIF not in overlay._toolbar.buttons
    QTest.keyClick(overlay, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    assert overlay.record_setup is None
    overlay.close()


def test_record_mode_asks_format_then_records(qapp):
    from klick import config
    for fmt, expected in (("video", Action.RECORD), ("gif", Action.GIF)):
        shot, _ = make_shot()
        session = CaptureSession([shot], Action.RECORD)
        actions = []
        session.finished.connect(lambda action, selection: actions.append(action))
        session.start()
        overlay = session.overlays[0]
        drag(overlay, QPoint(10, 10), QPoint(50, 50))
        assert overlay.record_setup is not None and actions == []  # antes pergunta formato, som e qualidade
        overlay.record_setup.format.set_value(fmt)
        QTest.keyClick(overlay, Qt.Key.Key_Return)
        assert actions == [expected]
    config.set_record_format("video")


def test_click_outside_keeps_the_selection(qapp):
    shot, _ = make_shot()
    session = CaptureSession([shot])
    session.start()
    overlay = session.overlays[0]
    drag(overlay, QPoint(10, 10), QPoint(50, 50))
    before = overlay.selection
    QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 300))
    assert overlay.selection == before and overlay._toolbar.isVisible()  # um clique solto não recomeça o print
    drag(overlay, QPoint(100, 100), QPoint(160, 140))
    assert overlay.selection != before  # arrastar de verdade, sim
    overlay.close()


def test_record_setup_passes_sound_and_quality(qapp):
    shot, _ = make_shot()
    session = CaptureSession([shot])
    got = []
    session.finished.connect(lambda action, selection: got.append(selection))
    session.start()
    session._overlays = [SelectionOverlay(shot, Action.RECORD)]
    session._overlays[0].selected.connect(session._on_selected)
    overlay = session.overlays[0]
    overlay.show()
    drag(overlay, QPoint(10, 10), QPoint(50, 50))
    setup = overlay.record_setup
    setup.sound.buttons["both"].click()
    setup.quality.buttons["high"].click()
    setup.start.click()
    [selection] = got
    assert (selection.sound, selection.quality) == ("both", "high")
    from klick import config
    assert (config.record_audio(), config.record_quality()) == ("both", "high")  # vira o padrão
    config.set_record_audio("none")
    config.set_record_quality("medium")


def test_record_setup_esc_goes_back_to_selecting(qapp):
    shot, _ = make_shot()
    overlay = SelectionOverlay(shot, Action.RECORD)
    overlay.show()
    drag(overlay, QPoint(10, 10), QPoint(50, 50))
    setup = overlay.record_setup
    assert setup is not None
    setup.format.set_value("gif")
    assert not setup.sound.isVisibleTo(setup)  # GIF não tem som
    QTest.keyClick(overlay, Qt.Key.Key_Escape)
    assert overlay.record_setup is None and not overlay._toolbar.isVisible()
    overlay.close()


def test_loupe_can_be_turned_off(qapp):
    from klick import config
    config.set_option("loupe", False)
    try:
        shot, _ = make_shot()
        overlay = SelectionOverlay(shot)
        assert overlay._loupe is False
        overlay.close()
    finally:
        config.set_option("loupe", True)


def test_mark_happens_inside_the_capture(qapp):
    shot, _ = make_shot()
    session = CaptureSession([shot])
    results = []
    session.finished.connect(lambda action, selection: results.append((action, selection)))
    session.start()
    overlay = session.overlays[0]
    drag(overlay, QPoint(10, 10), QPoint(110, 90))
    QTest.keyClick(overlay, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
    assert overlay.marking and results == []  # Marcar não fecha a captura
    assert not overlay._toolbar.isVisible()
    QTest.keyClick(overlay, Qt.Key.Key_P)  # Ocultar
    drag(overlay, QPoint(20, 20), QPoint(60, 60))
    assert len(overlay.marker.shapes) == 1
    QTest.keyClick(overlay, Qt.Key.Key_Return)
    [(action, selection)] = results
    assert action is Action.COPY and selection.marked
    assert selection.image.size() == QRect(0, 0, 100, 80).size()


def test_escape_leaves_mark_mode_first(qapp):
    shot, _ = make_shot()
    session = CaptureSession([shot])
    cancelled = []
    session.cancelled.connect(lambda: cancelled.append(True))
    session.start()
    overlay = session.overlays[0]
    drag(overlay, QPoint(10, 10), QPoint(110, 90))
    overlay.enter_mark()
    QTest.keyClick(overlay, Qt.Key.Key_Escape)
    assert not overlay.marking and overlay._toolbar.isVisible() and cancelled == []
    QTest.keyClick(overlay, Qt.Key.Key_Escape)
    assert cancelled == [True]


def test_c_copies_color_under_cursor(qapp):
    shot, _ = make_shot()
    overlay = SelectionOverlay(shot)
    overlay.show()
    QTest.mouseMove(overlay, QPoint(30, 30))  # dentro do bloco vermelho
    QTest.keyClick(overlay, Qt.Key.Key_C)
    assert QGuiApplication.clipboard().text() == "#FF0000"
    overlay.close()
