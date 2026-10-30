from datetime import datetime, timedelta
from types import SimpleNamespace

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage

from klick import config, sql
from klick.history import Collection, History
from klick.hotkeys import combo, key_name
from klick.ocr import OcrResult, Word


def image(color: str = "white") -> QImage:
    img = QImage(40, 30, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


def test_keep_copies_print_and_text_to_their_folders(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "save_dir", lambda: tmp_path / "Klick")
    history = History(tmp_path / "h", run_ocr=False)
    shot = history.add(image(), "copy", temp=True)
    read = history.add(image(), "ocr", text="pedido 15147800", temp=True)
    assert history.temp_count() == 2 and history.get(shot).temp
    saved = history.keep(shot)
    assert saved.parent == tmp_path / "Klick" / "Prints" and saved.exists()
    text = history.keep(read)
    assert text.suffix == ".txt" and text.read_text(encoding="utf-8") == "pedido 15147800"
    assert history.temp_count() == 0 and history.get(shot).saved == saved
    history.close()


def test_keep_moves_a_temporary_recording(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "save_dir", lambda: tmp_path / "Klick")
    history = History(tmp_path / "h", run_ocr=False)
    history.media_dir.mkdir(parents=True)
    clip = history.media_dir / "klick_1.mp4"
    clip.write_bytes(b"x")
    entry_id = history.add_media(clip, "video", image(), 2.0, temp=True)
    moved = history.keep(entry_id)
    assert not clip.exists() and moved == tmp_path / "Klick" / "Gravações" / "klick_1.mp4" and moved.exists()
    assert history.get(entry_id).media == moved
    history.close()


def test_expire_removes_only_old_temporary_items(qapp, tmp_path):
    history = History(tmp_path / "h", run_ocr=False)
    old_temp = history.add(image(), "copy", temp=True)
    old_kept = history.add(image(), "copy")
    new_temp = history.add(image(), "copy", temp=True)
    later = datetime.now() + timedelta(days=8)
    with history._db:
        history._db.execute("UPDATE captures SET created_at = ? WHERE id = ?",
                            ((datetime.now() - timedelta(days=1)).isoformat(timespec="seconds"), new_temp))
    assert history.expire(0) == 0  # 0 = nunca
    assert history.get(new_temp).expires_in(7) in (5, 6)
    assert history.expire(7, now=later) == 2
    assert [e.id for e in history.search()] == [old_kept]
    assert history.get(old_temp) is None
    history.close()


def test_save_policy_defaults_and_old_autosave(qapp):
    assert config.save_policy("prints") == "gallery" and config.save_policy("recordings") == "folder"
    config._settings().setValue("options/autosave", True)
    try:
        assert config.save_policy("prints") == "folder"  # quem salvava tudo continua salvando
    finally:
        config._settings().remove("options/autosave")
    config.set_temp_days(30)
    assert config.temp_days() == 30
    config.set_temp_days(7)


def test_hotkey_labels_and_recorded_keys():
    assert config.hotkey_label("<print_screen>") == "PrtSc"
    assert config.hotkey_label("<ctrl>+<shift>+t") == "Ctrl+Shift+T"
    assert config.hotkey_label("<f7>") == "F7"
    assert config.hotkey_label("<255>") == "Tecla 255"
    assert combo(["t", "<shift>", "<ctrl>"]) == "<ctrl>+<shift>+t"
    from pynput.keyboard import Key, KeyCode
    assert key_name(Key.f7) == "<f7>" and key_name(Key.ctrl_l) == "<ctrl>"
    assert key_name(KeyCode.from_vk(0x54)) == "t"  # Ctrl+T chega como código, não como letra
    assert key_name(KeyCode.from_vk(255)) == "<255>"  # tecla especial do FN: fica o código


def test_settings_reject_a_shortcut_already_in_use(qapp):
    from klick.settings_ui import SettingsDialog
    dialog = SettingsDialog(None)
    changed = []
    dialog.hotkeysChanged.connect(lambda: changed.append(True))
    dialog._set_hotkey("record", config.hotkeys()["capture"])
    assert config.hotkeys()["record"] == "<f7>" and changed == [] and "já é o atalho" in dialog._hotkey_note.text()
    dialog._set_hotkey("record", "<ctrl>+<alt>+g")
    assert config.hotkeys()["record"] == "<ctrl>+<alt>+g" and changed == [True]
    dialog._reset_hotkeys()
    assert config.hotkeys() == config.DEFAULT_HOTKEYS
    dialog.close()


def test_query_summary_and_json_repair():
    q = ("select c.codcli from clientes c left join pedidos p on p.codcli = c.codcli "
         "where p.data >= '2026-10-01' and (p.total > 10 or p.x = 1) order by c.codcli desc;")
    assert sql.joins(q) == ["left join pedidos p on p.codcli = c.codcli"]
    assert sql.filters(q) == ["p.data >= '2026-10-01'", "AND (p.total > 10 or p.x = 1)"]
    assert sql.ordering(q) == "c.codcli desc"
    r = sql.read_json("{'pedido': 15147800, 'itens': [{'cod': 1,}], ok: True,}")
    assert not r.error and r.value == {"pedido": 15147800, "itens": [{"cod": 1}], "ok": True}
    assert (r.keys, r.items, r.depth) == (4, 1, 3)
    assert sql.read_json('{"a": 1 "b": 2}').error == "linha 1, coluna 9: falta uma vírgula"


def test_column_stats_sum_brazilian_numbers():
    rows = [["Cod", "Preço", "Cliente"], ["1", "1.240,50", "Ana"], ["2", "R$ 7", ""], ["3", "", "Ana"]]
    cod, price, client = sql.column_stats(rows)
    assert (cod.kind, cod.sum) == ("número", 6)
    assert (price.kind, price.filled, price.sum, price.max) == ("número", 2, 1247.5, 1240.5)
    assert (client.kind, client.filled, client.distinct) == ("texto", 2, 1)
    assert sql.brl(1247.5) == "1.247,50" and sql.brl(6.0) == "6"


def json_result() -> OcrResult:
    lines = ['{"pedido": 15147800,', '"situacao": "faturado",', '"itens": [1, 2]}']
    words = []
    for i, line in enumerate(lines):
        x = 10
        for part in line.split():
            words.append(Word(part, QRectF(x, 10 + i * 24, 8 * len(part), 16), i))
            x += 8 * len(part) + 6
    return OcrResult(tuple(words), "RapidOCR", tuple(lines))


def test_analysis_opens_json_tab_formatted(qapp):
    from klick.sql_ui import AnalysisWindow
    window = AnalysisWindow(image(), json_result(), refine=False)
    assert window.tabs.value == "json" and sql.analysis_tab(json_result()) == "json"
    assert window.json_edit.toPlainText().startswith('{\n  "pedido": 15147800')
    assert window.json_state.text() == "Válido"
    window._format_json(compact=True)
    assert window.current_text() == '{"pedido":15147800,"situacao":"faturado","itens":[1,2]}'
    window.json_edit.setPlainText('{"a": 1 "b": 2}')
    window._update_json_info()
    assert window.json_state.text() == "Inválido" and "vírgula" in window.json_error.text()
    window.close()


def test_copied_print_follows_the_save_policy(qapp, tmp_path, monkeypatch):
    from test_app import make_app

    from klick.actions import Action
    monkeypatch.setattr(config, "save_dir", lambda: tmp_path / "Klick")
    klick = make_app(tmp_path)
    monkeypatch.setattr(klick, "_show_toast", lambda toast: None)
    klick._deliver(Action.COPY, image())
    [entry] = klick._history.search(collection=Collection.PRINTS)
    assert entry.temp and not (tmp_path / "Klick" / "Prints").exists()
    config.set_save_policy("prints", "folder")
    try:
        klick._deliver(Action.COPY, image("red"))
        newest = klick._history.search(collection=Collection.PRINTS)[0]
        assert not newest.temp and newest.saved.parent == tmp_path / "Klick" / "Prints"
    finally:
        config.set_save_policy("prints", "gallery")


def test_analysis_tab_ignores_plain_text():
    words = (Word("Bom", QRectF(0, 0, 30, 16), 0), Word("dia", QRectF(40, 0, 30, 16), 0))
    assert sql.analysis_tab(OcrResult(words, "x")) is None
    assert sql.analysis_tab(SimpleNamespace(words=(), text="")) is None
