"""Biblioteca de consultas: o banco, a página Consultas da galeria e o Guardar consulta da Análise."""

from concurrent.futures import Future

from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

from klick import config
from klick.history import History
from klick.library import Library, suggest_name

QUERY = "select c.codcli, c.nome from clientes c join pedidos p on p.codcli = c.codcli where p.valor > 10"


def image() -> QImage:
    img = QImage(300, 120, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    return img


def test_add_search_use_and_order(tmp_path):
    lib = Library(tmp_path / "consultas.db")
    a = lib.add("Pedidos acima de 10", QUERY)
    b = lib.add("Estoque baixo", "select codprod, estoque from produtos where estoque < 5")
    assert [q.name for q in lib.search("pedidos")] == ["Pedidos acima de 10"]  # no nome
    assert [q.name for q in lib.search("estoque produtos")] == ["Estoque baixo"]  # no texto, todas as palavras
    lib.used(b)
    assert [q.id for q in lib.search()] == [b, a]  # a mais usada em cima
    assert lib.get(a).tables == ["clientes", "pedidos"]
    assert lib.find_text(QUERY.upper().replace(" ", "  ")).id == a  # mesmo texto, outro espaçamento
    lib.update(a, name="Pedidos > 10", text="select 1")
    assert (lib.get(a).name, lib.get(a).text) == ("Pedidos > 10", "select 1")
    lib.delete(a)
    assert lib.count() == 1 and Library(tmp_path / "consultas.db").count() == 1  # ficou no disco
    lib.close()


def test_import_and_export(tmp_path):
    (tmp_path / "vendas_do_mes.sql").write_text("select * from vendas;", encoding="utf-8")
    (tmp_path / "repetida.sql").write_text("select * from vendas;", encoding="utf-8")
    (tmp_path / "vazia.sql").write_text("  ", encoding="utf-8")
    lib = Library(tmp_path / "consultas.db")
    # em ordem: entra "repetida"; "vendas_do_mes" tem o mesmo texto e a vazia não tem nada
    assert lib.import_files(sorted(tmp_path.glob("*.sql"))) == 1
    lib.add("Clientes", "select * from clientes")
    assert lib.export() == "-- Clientes\nselect * from clientes;\n\n-- repetida\nselect * from vendas;\n"
    lib.close()


def test_suggested_name():
    assert suggest_name(QUERY) == "SELECT clientes + pedidos"
    assert suggest_name("update produtos set preco = 1 where codprod = 5") == "UPDATE produtos"
    assert suggest_name("bom dia") == "Consulta"


def test_gallery_page_lists_edits_and_copies(qapp, tmp_path, monkeypatch):
    from klick.history_ui import HistoryWindow
    lib = Library(tmp_path / "consultas.db")
    first = lib.add("Pedidos acima de 10", QUERY)
    lib.add("Estoque baixo", "select codprod from produtos where estoque < 5")
    window = HistoryWindow(History(tmp_path / "h", run_ocr=False), lib)
    window.show()
    window.show_library(first)
    page = window._library_page
    assert window._heading.text() == "Consultas" and window._library_item.count == 2
    assert page.list.count() == 2 and page.name.text() == "Pedidos acima de 10"
    page.editor.setPlainText("select 1 from dual")  # editou: guarda sozinho
    page._save()
    assert lib.get(first).text == "select 1 from dual"
    window._copy_selected()  # Ctrl+C na galeria copia a consulta escolhida
    assert QGuiApplication.clipboard().text() == "select 1 from dual" and lib.get(first).uses == 1
    window._search.setText("estoque")
    window.refresh()
    assert page.list.count() == 1 and page.name.text() == "Estoque baixo"
    window._search.setText("nada disso")
    window.refresh()
    assert page._right.currentWidget() is page._empty and "nada disso" in page._empty_title.text()
    monkeypatch.setattr("klick.library_ui.confirm", lambda *a: True)
    window._search.setText("")
    window.refresh()
    page.select(first)
    window._delete_selected()
    assert lib.get(first) is None and page.list.count() == 1
    window.show_collection(None)  # volta para as capturas
    assert not window.library_mode and window._stack.currentWidget() is not page
    window.close()
    lib.close()


def test_new_query_from_the_page(qapp, tmp_path):
    from klick.library_ui import LibraryPage
    lib = Library(tmp_path / "consultas.db")
    page = LibraryPage(lib)
    page.show()
    page.refresh()
    assert page._right.currentWidget() is page._empty and "Nenhuma consulta guardada" in page._empty_title.text()
    page.new_query()
    assert lib.count() == 1 and page.name.text() == "Nova consulta"
    page.name.setText("Clientes de SP")
    page._autosave.start()
    page._save()
    assert lib.search()[0].name == "Clientes de SP"
    page.close()
    lib.close()


def test_analysis_keeps_the_query_with_a_name(qapp, tmp_path, monkeypatch):
    from test_analysis_ui import QUERY as LINES, lines_result

    from klick.analysis_ui import AnalysisWindow
    lib = Library(tmp_path / "consultas.db")
    window = AnalysisWindow(image(), lines_result(LINES), refine=False, library=lib)
    monkeypatch.setattr("klick.analysis_ui.QInputDialog.getText", lambda *a, **k: ("Clientes com pedido", True))
    window.keep_query.click()
    [saved] = lib.search()
    assert saved.name == "Clientes com pedido" and saved.text == window.sql.toPlainText()
    window.keep_query.click()  # de novo: já está
    assert lib.count() == 1 and "já está na biblioteca" in window.message.text()
    window.close()
    lib.close()


def test_folder_policy_file_gets_the_corrections(qapp, tmp_path, monkeypatch):
    from test_analysis_ui import QUERY as LINES, lines_result
    from test_app import make_app

    from klick import ocr
    monkeypatch.setattr(config, "save_dir", lambda: tmp_path / "Klick")
    monkeypatch.setattr(ocr, "precise_available", lambda: False)
    done: Future = Future()
    done.set_result(lines_result(LINES))
    monkeypatch.setattr(ocr, "recognize_words", lambda image, language=None: done)
    klick = make_app(tmp_path)
    config.set_save_policy("reading", "folder")
    try:
        window = klick._open_sql(image())
        QApplication.processEvents()
        QApplication.processEvents()
        [entry] = klick._history.search()
        assert entry.saved is not None and entry.saved.exists()
        window.sql.setPlainText("SELECT corrigido FROM clientes")
        window.close()
        assert entry.saved.read_text(encoding="utf-8") == "SELECT corrigido FROM clientes"
        assert klick._history.get(entry.id).text == "SELECT corrigido FROM clientes"
    finally:
        config.set_save_policy("reading", "gallery")
