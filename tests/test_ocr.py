import sys
import time
from concurrent.futures import Future

import pytest
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from klick import app as app_module
from klick.actions import Action
from klick.app import KlickApp
from klick.ocr import OcrError, recognize, scale_for_ocr
from klick.overlay import CaptureSession

from test_overlay import drag, make_shot


def test_scale_upscales_small_selection():
    assert scale_for_ocr(QSize(400, 30), 10000) == 2.0


def test_scale_keeps_large_selection():
    assert scale_for_ocr(QSize(1920, 1080), 10000) == 1.0


def test_scale_shrinks_beyond_engine_limit():
    assert scale_for_ocr(QSize(20000, 500), 10000) == 0.5


@pytest.mark.skipif(sys.platform == "win32", reason="no Windows o OCR roda de verdade")
def test_recognize_outside_windows_reports_error():
    with pytest.raises(OcrError):
        recognize(QImage(10, 10, QImage.Format.Format_RGB32)).result()


def test_ctrl_t_triggers_ocr(qapp):
    shot, _ = make_shot()
    session = CaptureSession([shot])
    actions = []
    session.finished.connect(lambda action, image: actions.append(action))
    session.start()
    overlay = session.overlays[0]
    drag(overlay, QPoint(10, 10), QPoint(50, 50))
    QTest.keyClick(overlay, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)
    assert actions == [Action.OCR]


def wait_for(predicate, timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def done(value: str = "", error: Exception | None = None) -> Future:
    future = Future()
    if error:
        future.set_exception(error)
    else:
        future.set_result(value)
    return future


def test_ocr_result_goes_to_clipboard(qapp, monkeypatch):
    monkeypatch.setattr(app_module.ocr, "recognize", lambda image, language=None: done("Erro 500\nInternal"))
    klick = KlickApp(QApplication.instance())
    QGuiApplication.clipboard().clear()
    klick._on_finished(Action.OCR, QImage(10, 10, QImage.Format.Format_RGB32))
    assert wait_for(lambda: QGuiApplication.clipboard().text() == "Erro 500\nInternal", 1000)
    assert not klick._ocr_pending


def test_ocr_without_text_keeps_clipboard(qapp, monkeypatch):
    monkeypatch.setattr(app_module.ocr, "recognize", lambda image, language=None: done("  \n"))
    klick = KlickApp(QApplication.instance())
    QGuiApplication.clipboard().setText("anterior")
    klick._on_finished(Action.OCR, QImage(10, 10, QImage.Format.Format_RGB32))
    assert wait_for(lambda: not klick._ocr_pending, 1000)
    assert QGuiApplication.clipboard().text() == "anterior"


def test_ocr_error_is_reported(qapp, monkeypatch):
    monkeypatch.setattr(app_module.ocr, "recognize",
                        lambda image, language=None: done(error=OcrError("sem idioma")))
    warnings = []
    klick = KlickApp(QApplication.instance())
    monkeypatch.setattr(klick, "_warn", warnings.append)
    klick._on_finished(Action.OCR, QImage(10, 10, QImage.Format.Format_RGB32))
    assert wait_for(lambda: bool(warnings), 1000)
    assert "sem idioma" in warnings[0]


def test_ocr_result_from_worker_thread(qapp, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(app_module.ocr, "recognize",
                        lambda image, language=None: pool.submit(lambda: (time.sleep(0.05), "de outra thread")[1]))
    klick = KlickApp(QApplication.instance())
    klick._on_finished(Action.OCR, QImage(10, 10, QImage.Format.Format_RGB32))
    assert klick._ocr_pending
    assert wait_for(lambda: QGuiApplication.clipboard().text() == "de outra thread", 1000)
    pool.shutdown()
