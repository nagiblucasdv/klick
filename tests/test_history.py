import sqlite3
from pathlib import Path

from PySide6.QtGui import QColor, QImage

from klick import config
from klick.history import Collection, History, fts_query
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
    history.add(image("blue"), "save", text="tudo certo")
    history.add(image("red"), "ocr", text="erro lido")
    window = HistoryWindow(history)
    window.show()
    assert window._list.count() == 2  # prints: copiado e salvo; a leitura fica na coleção dela
    window.show_collection(Collection.READING)
    assert window._list.count() == 1
    window.show_collection(Collection.PRINTS)
    window._search.setText("erro")
    window.refresh()
    assert window._list.count() == 1
    assert window._tab_buttons[Collection.READING].count == 1  # contagem segue a busca
    window._search.setText("nada disso")
    window.refresh()
    assert window._stack.currentWidget() is window._empty
    window.close()


def test_collections_split_captures(qapp, tmp_path):
    history = History(tmp_path, run_ocr=False)
    history.add(image(), "copy", text="a")
    history.add(image(), "edit", text="b")
    history.add(image(), "ocr", text="c")
    video = history.add_media(Path("C:/videos/klick_1.mp4"), "video", image(), 12.4)
    history.add_media(Path("C:/videos/klick_2.gif"), "gif", image())
    history.add(image(), "sql", text="select 1")
    assert history.counts() == {Collection.PRINTS: 2, Collection.RECORDINGS: 1, Collection.GIFS: 1,
                                Collection.READING: 1, Collection.ANALYSIS: 1}
    entry = history.get(video)
    assert entry.collection is Collection.RECORDINGS
    assert entry.media == Path("C:/videos/klick_1.mp4") and entry.duration == 12.4
    assert entry.thumb_path.exists() and not entry.image_path.exists()
    assert [e.id for e in history.search("klick_1")] == [video]  # o nome do arquivo é pesquisável


def test_old_database_gets_new_columns(qapp, tmp_path):
    db = sqlite3.connect(tmp_path / "history.db")
    db.executescript("""
        CREATE TABLE captures (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, source TEXT NOT NULL,
                               width INTEGER NOT NULL, height INTEGER NOT NULL, text TEXT NOT NULL DEFAULT '');
        INSERT INTO captures (created_at, source, width, height, text) VALUES ('2026-10-01T10:00:00', 'copy', 4, 4, '');
    """)
    db.close()
    history = History(tmp_path, run_ocr=False)
    [entry] = history.search()
    assert entry.kind == "image" and entry.collection is Collection.PRINTS


def test_delete_permanently_removes_media_file(qapp, tmp_path):
    from klick.history import History
    history = History(tmp_path / "h", run_ocr=False)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    frame = QImage(20, 20, QImage.Format.Format_RGB32)
    keep = history.add_media(clip, "video", frame, 2.0)
    history.delete(keep)
    assert clip.exists()  # só saiu da galeria
    gone = history.add_media(clip, "video", frame, 2.0)
    history.delete(gone, remove_file=True)
    assert not clip.exists() and history.get(gone) is None
    history.close()
