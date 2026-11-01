"""Painel de consultas (como o Windows + V): filtrar, escolher, colar ou só copiar, e o foco."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from klick import focus
from klick.analysis.schema import Schema
from klick.library import Library
from klick.quick_ui import QuickPanel


def make(tmp_path, tables: bool = True) -> tuple[QuickPanel, Library, Schema]:
    lib = Library(tmp_path / "consultas.db")
    lib.add("Pedidos faturados", "SELECT * FROM pedidos WHERE situacao = 'F'")
    lib.add("Estoque baixo", "SELECT codprod FROM produtos WHERE estoque < 5")
    schema = Schema(tmp_path / "estrutura.json")
    schema.learn_query("select c.codcli, c.nome from clientes c")
    panel = QuickPanel(lib, schema, tables=tables)
    panel.show_at(QPoint(300, 300))
    return panel, lib, schema


def test_typing_filters_and_enter_pastes(qapp, tmp_path):
    panel, lib, _ = make(tmp_path)
    chosen = []
    panel.chosen.connect(lambda text, paste: chosen.append((text, paste)))
    assert panel.list.count() == 2 and panel.focusWidget() is panel.search  # pronto para digitar
    QTest.keyClicks(panel.search, "estoque")
    assert panel.list.count() == 1
    QTest.keyClick(panel.search, Qt.Key.Key_Return)
    assert chosen == [("SELECT codprod FROM produtos WHERE estoque < 5", True)]
    assert lib.search("estoque")[0].uses == 1 and not panel.isVisible()
    lib.close()


def test_ctrl_enter_only_copies_and_arrows_choose(qapp, tmp_path):
    panel, lib, _ = make(tmp_path)
    chosen = []
    panel.chosen.connect(lambda text, paste: chosen.append((text, paste)))
    QTest.keyClick(panel.search, Qt.Key.Key_Down)
    QTest.keyClick(panel.search, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    # a lista vem das mais usadas e mais novas: Estoque baixo, depois Pedidos faturados
    assert chosen == [("SELECT * FROM pedidos WHERE situacao = 'F'", False)]
    lib.close()


def test_tables_tab_and_templates(qapp, tmp_path):
    panel, lib, _ = make(tmp_path)
    chosen = []
    panel.chosen.connect(lambda text, paste: chosen.append(text))
    QTest.keyClick(panel.search, Qt.Key.Key_Tab)
    assert panel.tabs.value == "tables" and panel.template.isVisible() and panel.list.count() == 1
    QTest.keyClick(panel.search, Qt.Key.Key_Right)
    assert panel.template.value == "insert"
    QTest.keyClick(panel.search, Qt.Key.Key_Return)
    assert chosen == ["INSERT INTO clientes (codcli, nome)\nVALUES (/* codcli */, /* nome */);"]
    lib.close()


def test_escape_cancels_and_empty_states(qapp, tmp_path):
    lib = Library(tmp_path / "vazia.db")
    panel = QuickPanel(lib, Schema(tmp_path / "e.json"), tables=False)
    cancelled = []
    panel.cancelled.connect(lambda: cancelled.append(True))
    panel.show_at(QPoint(10, 10))
    assert len(panel.tabs.buttons) == 1 and "Nenhuma consulta guardada" in panel.empty.text()
    QTest.keyClick(panel.search, Qt.Key.Key_Return)  # nada para escolher: não quebra nem fecha
    assert panel.isVisible()
    QTest.keyClick(panel.search, Qt.Key.Key_Escape)
    assert cancelled == [True] and not panel.isVisible()
    lib.close()


def test_app_pastes_into_the_previous_window(qapp, tmp_path, monkeypatch):
    from test_app import make_app
    from test_ocr import wait_for
    calls = []
    monkeypatch.setattr(focus, "foreground", lambda: 4242)
    monkeypatch.setattr(focus, "caret_or_cursor", lambda: QPoint(200, 200))
    monkeypatch.setattr(focus, "give_back", lambda hwnd: calls.append(("volta", hwnd)))
    monkeypatch.setattr(focus, "paste", lambda: calls.append(("cola",)))
    klick = make_app(tmp_path)
    klick._library.add("Clientes", "SELECT * FROM clientes")
    klick.show_queries()
    panel = klick._panel
    panel.search.setText("clientes")
    QTest.keyClick(panel.search, Qt.Key.Key_Return)
    assert QGuiApplication.clipboard().text() == "SELECT * FROM clientes"
    assert wait_for(lambda: len(calls) == 2, 1000) and calls == [("volta", 4242), ("cola",)]
    klick.show_queries()
    klick.show_queries()  # o atalho de novo fecha o painel aberto
    assert not klick._panel
