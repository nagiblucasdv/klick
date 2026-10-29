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
