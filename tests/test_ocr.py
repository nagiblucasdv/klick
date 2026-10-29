import sys
import time
from concurrent.futures import Future

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from klick import app as app_module
from klick.actions import Action
from klick.app import KlickApp
from klick.capture import Selection
from klick.history import History
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


def test_ctrl_t_opens_reading(qapp):
    shot, _ = make_shot()
    session = CaptureSession([shot])
    actions = []
    session.finished.connect(lambda action, selection: actions.append(action))
    session.start()
    overlay = session.overlays[0]
    drag(overlay, QPoint(10, 10), QPoint(50, 50))
    QTest.keyClick(overlay, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)
    assert actions == [Action.READ]


def wait_for(predicate, timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def make_app(tmp_path) -> KlickApp:
    return KlickApp(QApplication.instance(), history=History(tmp_path, run_ocr=False))


def selection() -> Selection:
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    return Selection(image, QRect(0, 0, 10, 10), QRect(0, 0, 10, 10), QGuiApplication.primaryScreen())


def done(value: str = "", error: Exception | None = None) -> Future:
    future = Future()
    if error:
        future.set_exception(error)
    else:
        future.set_result(value)
    return future


def test_ocr_result_goes_to_clipboard(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.ocr, "recognize_best", lambda image, language=None: done("Erro 500\nInternal"))
    klick = make_app(tmp_path)
    QGuiApplication.clipboard().clear()
    klick._on_finished(Action.OCR, selection())
    assert wait_for(lambda: QGuiApplication.clipboard().text() == "Erro 500\nInternal", 1000)
    assert not klick._ocr_pending


def test_ocr_without_text_keeps_clipboard(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.ocr, "recognize_best", lambda image, language=None: done("  \n"))
    klick = make_app(tmp_path)
    QGuiApplication.clipboard().setText("anterior")
    klick._on_finished(Action.OCR, selection())
    assert wait_for(lambda: not klick._ocr_pending, 1000)
    assert QGuiApplication.clipboard().text() == "anterior"


def test_ocr_error_is_reported(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.ocr, "recognize_best",
                        lambda image, language=None: done(error=OcrError("sem idioma")))
    warnings = []
    klick = make_app(tmp_path)
    monkeypatch.setattr(klick, "_warn", warnings.append)
    klick._on_finished(Action.OCR, selection())
    assert wait_for(lambda: bool(warnings), 1000)
    assert "sem idioma" in warnings[0]


def test_ocr_result_from_worker_thread(qapp, monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(app_module.ocr, "recognize_best",
                        lambda image, language=None: pool.submit(lambda: (time.sleep(0.05), "de outra thread")[1]))
    klick = make_app(tmp_path)
    klick._on_finished(Action.OCR, selection())
    assert klick._ocr_pending
    assert wait_for(lambda: QGuiApplication.clipboard().text() == "de outra thread", 1000)
    pool.shutdown()


def test_ocr_text_is_stored_in_history(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.ocr, "recognize_best", lambda image, language=None: done("Atenção: erro 500"))
    klick = make_app(tmp_path)
    klick._on_finished(Action.OCR, selection())
    assert wait_for(lambda: bool(klick._history.search("atencao")), 1000)


@pytest.mark.skipif(not __import__("klick.ocr", fromlist=["x"]).precise_available(), reason="RapidOCR não instalado")
def test_precise_positions_are_in_original_pixels(qapp):
    from PySide6.QtGui import QColor, QFont, QPainter

    from klick.ocr import recognize_precise

    image = QImage(420, 60, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    p = QPainter(image)
    font = QFont("Segoe UI")
    font.setPixelSize(26)
    p.setFont(font)
    p.setPen(QColor("black"))
    p.drawText(10, 40, "Pedido 48213 faturado")  # rente à borda, como numa seleção apertada
    p.end()
    result = recognize_precise(image).result(timeout=180)
    assert result.text == "Pedido 48213 faturado"
    first = result.words[0].rect
    assert 0 <= first.left() <= 20 and 5 <= first.top() <= 25  # sem o deslocamento da margem interna
