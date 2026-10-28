from PySide6.QtGui import QColor, QImage

from klick import config
from klick.history import History, fts_query
from klick.history_ui import HistoryWindow


def image(color="white") -> QImage:
    img = QImage(400, 200, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


def test_fts_query_quotes_terms():
    assert fts_query('erro "500') == '"erro"* """500"*'
    assert fts_query("   ") == ""


def test_search_ignores_case_and_accents(qapp, tmp_path):
    history = History(tmp_path, run_ocr=False)
    history.add(image(), "copy", text="Atenção: Erro 500 - Internal Server Error")
    history.add(image(), "copy", text="Pedido 1234 faturado")
    assert [e.text[:7] for e in history.search("atencao erro")] == ["Atenção"]
    assert len(history.search("fatur")) == 1  # prefixo
    assert history.search("inexistente") == []
    assert len(history.search("")) == 2


def test_add_saves_image_and_thumbnail(qapp, tmp_path):
    history = History(tmp_path, run_ocr=False)
    entry_id = history.add(image(), "save")
    entry = history.get(entry_id)
    assert entry.image_path.exists() and entry.thumb_path.exists()
    assert QImage(str(entry.thumb_path)).width() == 320


def test_ocr_text_set_later_becomes_searchable(qapp, tmp_path):
    history = History(tmp_path, run_ocr=False)
    entry_id = history.add(image(), "copy")
    assert history.search("boleto") == []
    history.set_text(entry_id, "Boleto vencido")
    assert [e.id for e in history.search("boleto")] == [entry_id]


def test_delete_removes_files(qapp, tmp_path):
    history = History(tmp_path, run_ocr=False)
    entry = history.get(history.add(image(), "copy", text="x"))
    history.delete(entry.id)
    assert history.get(entry.id) is None
    assert not entry.image_path.exists() and not entry.thumb_path.exists()
    assert history.search("x") == []


def test_prune_keeps_newest(qapp, tmp_path):
    history = History(tmp_path, run_ocr=False)
    ids = [history.add(image(), "copy", text=f"item{i}") for i in range(5)]
    history.prune(2)
    assert [e.id for e in history.search()] == ids[:-3:-1]
    assert len(list((tmp_path / "images").iterdir())) == 4


def test_disabled_history_stores_nothing(qapp, tmp_path):
    history = History(tmp_path, run_ocr=False)
    config.set_history_enabled(False)
    try:
        assert history.add(image(), "copy") is None
        assert history.search() == []
    finally:
        config.set_history_enabled(True)


def test_window_lists_and_filters(qapp, tmp_path):
    history = History(tmp_path, run_ocr=False)
    history.add(image(), "copy", text="erro 500")
    history.add(image("red"), "ocr", text="tudo certo")
    window = HistoryWindow(history)
    window.show()
    assert window._list.count() == 2
    window._search.setText("erro")
    window.refresh()
    assert window._list.count() == 1
    window._search.setText("nada disso")
    window.refresh()
    assert window._stack.currentWidget() is window._empty
    window.close()
