from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolButton

from klick.actions import Action
from klick.editor import Box, EditorWindow, Number, Pixelate, Style, Tool, render


def white(w=200, h=120) -> QImage:
    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    return image


def stripes(w=120, h=60) -> QImage:
    image = white(w, h)
    for x in range(0, w, 2):
        for y in range(h):
            image.setPixelColor(x, y, QColor("black"))
    return image


def drag(widget, start, end):
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(widget, end)
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)


def test_rect_is_drawn_in_image_pixels(qapp):
    out = render(white(), [Box(QRectF(20, 20, 100, 60), Style(QColor("red"), 1.0))])
    assert out.pixelColor(20, 50) == QColor("red")
    assert out.pixelColor(70, 50) == QColor("white")


def test_pixelate_hides_detail(qapp):
    base = stripes()
    out = render(base, [Pixelate(QRectF(0, 0, 120, 60), Style(QColor("red"), 1.0))])
    # Listras de 1 px viram blocos cinza uniformes.
    a, b = out.pixelColor(10, 10), out.pixelColor(11, 10)
    assert a == b
    assert 60 < a.red() < 200


def test_number_render(qapp):
    out = render(white(), [Number(QPointF(50, 50), 1, Style(QColor("#3b82f6"), 1.0))])
    assert out.pixelColor(50, 42) != QColor("white")


def test_editor_draws_with_mouse_and_undo(qapp):
    editor = EditorWindow(white(400, 300), image_scale=1.0)
    editor.show()
    canvas = editor.canvas
    editor.set_tool(Tool.RECT)
    drag(canvas, QPoint(10, 10), QPoint(80, 60))
    assert len(canvas.shapes) == 1
    editor.set_tool(Tool.NUMBER)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(150, 150))
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 150))
    assert [s.value for s in canvas.shapes if isinstance(s, Number)] == [1, 2]
    canvas.undo()
    assert canvas.next_number == 2
    canvas.undo()
    canvas.undo()
    assert canvas.shapes == []
    editor.close()


def test_tiny_drag_does_not_create_shape(qapp):
    editor = EditorWindow(white(400, 300))
    editor.show()
    editor.set_tool(Tool.ARROW)
    drag(editor.canvas, QPoint(10, 10), QPoint(11, 11))
    assert editor.canvas.shapes == []
    editor.close()


def test_hidpi_canvas_maps_to_image_pixels(qapp):
    # Print de tela a 200%: 400x300 físicos mostrados em 200x150 lógicos.
    editor = EditorWindow(white(400, 300), image_scale=2.0)
    editor.show()
    assert editor.canvas.width() == 200
    editor.set_tool(Tool.RECT)
    drag(editor.canvas, QPoint(10, 10), QPoint(50, 50))
    assert editor.canvas.shapes[0].rect.normalized() == QRectF(20, 20, 80, 80)
    editor.close()


def test_copy_emits_rendered_image(qapp):
    editor = EditorWindow(white(400, 300))
    editor.show()
    editor.set_tool(Tool.RECT)
    drag(editor.canvas, QPoint(10, 10), QPoint(80, 60))
    results = []
    editor.done.connect(lambda action, image: results.append((action, image)))
    copy = next(b for b in editor.findChildren(QToolButton) if b.text() == "Copiar")
    copy.click()
    [(action, image)] = results
    assert action is Action.COPY
    assert image.pixelColor(10, 30) == QColor("#ef4444")  # borda do retângulo, cor padrão
