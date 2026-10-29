from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtTest import QTest

from klick.ocr import OcrResult, Word
from klick.reader import ReaderWindow


def result() -> OcrResult:
    words = [Word("Erro", QRectF(10, 10, 40, 16), 0), Word("500:", QRectF(56, 10, 40, 16), 0),
             Word("falha", QRectF(102, 10, 46, 16), 0), Word("Tabela", QRectF(10, 40, 56, 16), 1),
             Word("012", QRectF(72, 40, 30, 16), 1)]
    return OcrResult(tuple(words), "pt-BR", ("Erro 500: falha", "Tabela 012"))


def page() -> QImage:
    image = QImage(200, 70, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    return image


def at(window: ReaderWindow, x: float, y: float) -> QPoint:
    return QPoint(round(x * window.view.scale), round(y * window.view.scale))


def test_text_between_joins_lines():
    r = result()
    assert r.text_between(1, 3) == "500: falha\nTabela"
    assert r.text_between(4, 0) == r.text_between(0, 4)
    assert r.text == "Erro 500: falha\nTabela 012"


def test_drag_selects_words_in_reading_order(qapp):
    window = ReaderWindow(page(), result())
    window.show()
    view = window.view
    QTest.mousePress(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, 70, 18))
    QTest.mouseMove(view, at(window, 80, 48))
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, 80, 48))
    assert view.selected_text() == "500: falha\nTabela 012"
    assert window.copy_sel.isEnabled()
    window.copy_sel.click()
    assert QGuiApplication.clipboard().text() == "500: falha\nTabela 012"
    window.close()


def test_double_click_takes_the_line(qapp):
    window = ReaderWindow(page(), result())
    window.show()
    QTest.mouseDClick(window.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, 20, 48))
    assert window.view.selected_text() == "Tabela 012"
    window.close()


def test_empty_result_shows_message(qapp):
    window = ReaderWindow(page(), OcrResult())
    assert window.view.message
    assert not window.copy_all.isEnabled()
    window.close()


def fast_then_precise(monkeypatch):
    """Simula os dois motores: o rápido e o preciso entregam quando o teste mandar."""
    from concurrent.futures import Future

    from klick import ocr

    futures = {"fast": Future(), "precise": Future()}
    monkeypatch.setattr(ocr, "recognize_words", lambda image, language=None: futures["fast"])
    monkeypatch.setattr(ocr, "recognize_precise", lambda image: futures["precise"])
    monkeypatch.setattr(ocr, "precise_available", lambda: True)
    return futures


def precise_result() -> OcrResult:
    words = [Word("Erro", QRectF(10, 10, 40, 16), 0), Word("500:", QRectF(56, 10, 40, 16), 0),
             Word("marcados", QRectF(102, 10, 70, 16), 0)]
    return OcrResult(tuple(words), "RapidOCR", ("Erro 500: marcados",))


def test_precise_result_replaces_fast_one(qapp, monkeypatch):
    from test_ocr import wait_for

    futures = fast_then_precise(monkeypatch)
    window = ReaderWindow(page())
    recognized = []
    window.recognized.connect(recognized.append)
    futures["fast"].set_result(result())
    assert wait_for(lambda: window.view.result is not None, 1000)
    assert "refinando" in window.status.text() and recognized == []
    futures["precise"].set_result(precise_result())
    assert wait_for(lambda: window.view.result.language == "RapidOCR", 1000)
    assert window.text.toPlainText() == "Erro 500: marcados"
    assert "leitura precisa" in window.status.text()
    assert [r.language for r in recognized] == ["RapidOCR"]
    window.close()


def test_precise_result_does_not_overwrite_corrections(qapp, monkeypatch):
    from test_ocr import wait_for

    futures = fast_then_precise(monkeypatch)
    window = ReaderWindow(page())
    futures["fast"].set_result(result())
    assert wait_for(lambda: window.view.result is not None, 1000)
    window.text.setPlainText("texto corrigido")
    futures["precise"].set_result(precise_result())
    assert wait_for(lambda: "corrigiu" in window.status.text(), 1000)
    assert window.text.toPlainText() == "texto corrigido"
    window.copy_all.click()
    assert QGuiApplication.clipboard().text() == "texto corrigido"
    window.close()


def test_selecting_in_text_panel_marks_words(qapp):
    from PySide6.QtGui import QTextCursor

    window = ReaderWindow(page(), result())
    cursor = window.text.textCursor()
    cursor.setPosition(5)  # dentro de "500:"
    cursor.setPosition(12, QTextCursor.MoveMode.KeepAnchor)  # dentro de "falha"
    window.text.setTextCursor(cursor)
    assert window.view.selected_range() == (1, 2)
    window.close()
