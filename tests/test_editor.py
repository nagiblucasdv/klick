from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtTest import QTest

from klick.actions import Action
from klick.editor import (PALETTE, Arrow, Box, EditorWindow, Highlight, Marker, Measure, Pixelate, Spotlight,
                          Step, Stroke, Style, Tool, render)


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


def style(color=PALETTE[1]) -> Style:
    return Style(QColor(color), 1.0)


def test_spotlight_dims_everything_else(qapp):
    out = render(white(), [Spotlight(QRectF(50, 30, 60, 40), style())])
    assert out.pixelColor(80, 50) == QColor("white")  # dentro: intacto
    assert out.pixelColor(5, 5).lightness() < 160  # fora: escurecido


def test_two_spotlights_dim_once(qapp):
    one = render(white(), [Spotlight(QRectF(10, 10, 20, 20), style())])
    two = render(white(), [Spotlight(QRectF(10, 10, 20, 20), style()), Spotlight(QRectF(100, 10, 20, 20), style())])
    assert one.pixelColor(180, 100) == two.pixelColor(180, 100)
    assert two.pixelColor(110, 20) == QColor("white")


def test_highlight_tints_like_a_marker(qapp):
    out = render(white(), [Highlight(QRectF(10, 10, 80, 20), style())])
    tinted = out.pixelColor(40, 20)
    assert tinted != QColor("white") and tinted.red() > tinted.blue()  # laranja sobre branco


def test_pixelate_hides_detail(qapp):
    base = stripes()
    out = render(base, [Pixelate(QRectF(0, 0, 120, 60), style())])
    # Listras de 1 px viram blocos cinza uniformes.
    a, b = out.pixelColor(10, 10), out.pixelColor(11, 10)
    assert a == b
    assert 60 < a.red() < 200


def test_step_render(qapp):
    out = render(white(), [Step(QPointF(50, 50), 1, style())])
    assert out.pixelColor(44, 44) != QColor("white")


def test_measure_reports_pixels_and_snaps(qapp):
    marker = Marker(white())
    marker.set_tool(Tool.MEASURE)
    marker.press(QPointF(10, 50))
    marker.move(QPointF(110, 53))  # quase horizontal: gruda
    marker.release(QPointF(110, 53))
    [measure] = marker.shapes
    assert isinstance(measure, Measure)
    assert measure.end == QPointF(110, 50) and measure.length == 100


def test_text_is_typed_inline(qapp):
    editor = EditorWindow(white(400, 300))
    editor.show()
    editor.set_tool(Tool.TEXT)
    QTest.mouseClick(editor.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 20))
    QTest.keyClicks(editor, "Tabela 012")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert [s.text for s in editor.shapes] == ["Tabela 012"]
    editor.close()


def test_pick_copies_color(qapp):
    image = white()
    image.setPixelColor(30, 30, QColor("#ff3b30"))
    marker = Marker(image)
    picked = []
    marker.picked.connect(picked.append)
    marker.set_tool(Tool.PICK)
    marker.press(QPointF(30.4, 30.4))
    assert picked == ["#FF3B30"]
    assert QGuiApplication.clipboard().text() == "#FF3B30"
    assert marker.shapes == []


def test_editor_draws_with_mouse_and_undo(qapp):
    editor = EditorWindow(white(400, 300), image_scale=1.0)
    editor.show()
    canvas = editor.canvas
    editor.set_tool(Tool.HIGHLIGHT)
    drag(canvas, QPoint(10, 10), QPoint(80, 60))
    assert len(editor.shapes) == 1
    editor.set_tool(Tool.STEP)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(150, 150))
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 150))
    assert [s.value for s in editor.shapes if isinstance(s, Step)] == [1, 2]
    editor.marker.undo()
    assert editor.marker.next_number == 2
    editor.marker.undo()
    editor.marker.undo()
    assert editor.shapes == []
    editor.close()


def test_tool_keys_switch_tools(qapp):
    editor = EditorWindow(white(400, 300))
    editor.show()
    QTest.keyClick(editor, Qt.Key.Key_A)
    assert editor.marker.tool is Tool.ARROW
    assert editor.bar.tools[Tool.ARROW].isChecked()
    QTest.keyClick(editor, Qt.Key.Key_C)
    assert editor.marker.color.name() == PALETTE[1]
    editor.close()


def test_tiny_drag_does_not_create_shape(qapp):
    editor = EditorWindow(white(400, 300))
    editor.show()
    editor.set_tool(Tool.ARROW)
    drag(editor.canvas, QPoint(10, 10), QPoint(11, 11))
    assert editor.shapes == []
    editor.close()


def test_hidpi_canvas_maps_to_image_pixels(qapp):
    # Print de tela a 200%: 400x300 físicos mostrados em 200x150 lógicos.
    editor = EditorWindow(white(400, 300), image_scale=2.0)
    editor.show()
    assert editor.canvas.width() == 200
    editor.set_tool(Tool.SPOT)
    drag(editor.canvas, QPoint(10, 10), QPoint(50, 50))
    assert editor.shapes[0].rect.normalized() == QRectF(20, 20, 80, 80)
    editor.close()


def test_copy_emits_rendered_image(qapp):
    editor = EditorWindow(white(400, 300))
    editor.show()
    editor.set_tool(Tool.SPOT)
    drag(editor.canvas, QPoint(100, 100), QPoint(200, 200))
    results = []
    editor.done.connect(lambda action, image: results.append((action, image)))
    editor.bar.done.click()
    [(action, image)] = results
    assert action is Action.COPY
    assert image.pixelColor(150, 150) == QColor("white")
    assert image.pixelColor(10, 10).lightness() < 160


def test_bar_shows_every_tool_and_swatches_pick_color(qapp):
    editor = EditorWindow(white(400, 300))
    editor.show()
    assert all(b.isVisibleTo(editor.bar) for b in editor.bar.tools.values())  # tudo à vista, sem abas
    QTest.keyClick(editor, Qt.Key.Key_R)
    assert editor.bar.tools[Tool.MEASURE].isChecked() and "Medir" in editor.bar.description.text()
    editor.bar.swatches[3].click()
    assert editor.marker.color.name() == PALETTE[3]
    editor.bar.size.buttons["thick"].click()
    editor.set_tool(Tool.ARROW)
    drag(editor.canvas, QPoint(10, 10), QPoint(90, 60))
    assert editor.shapes[0].style.width > style().width
    editor.close()


def test_box_ellipse_line_and_pen(qapp):
    marker = Marker(white())
    for tool in (Tool.BOX, Tool.ELLIPSE, Tool.LINE, Tool.PEN):
        marker.set_tool(tool)
        marker.press(QPointF(20, 20))
        marker.move(QPointF(60, 40))
        marker.move(QPointF(120, 61))
        marker.release(QPointF(120, 61))
    box, ellipse, line, pen = marker.shapes
    assert isinstance(box, Box) and not box.round_ and isinstance(ellipse, Box) and ellipse.round_
    assert isinstance(line, Arrow) and not line.head and line.end == QPointF(120, 61)
    assert isinstance(pen, Stroke) and len(pen.points) == 3
    out = marker.result()
    assert out.pixelColor(20, 40) != QColor("white")  # borda esquerda da caixa


def test_blur_softens_without_blocks(qapp):
    out = render(stripes(), [Pixelate(QRectF(0, 0, 120, 60), style(), soft=True)])
    a, b = out.pixelColor(30, 30), out.pixelColor(31, 30)
    assert abs(a.red() - b.red()) < 40 and 60 < a.red() < 200
