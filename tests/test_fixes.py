"""Bugs corrigidos na revisão de 31/10: cada teste é um caso que perdia arquivo, texto ou atalho."""

from concurrent.futures import Future

from PySide6.QtCore import QProcess
from PySide6.QtGui import QColor, QImage

from klick import config, ocr
from klick.actions import Action
from klick.history import History
from klick.ocr import OcrResult
from klick.recorder import Recorder, RecordFormat


def image(color: str = "white") -> QImage:
    img = QImage(40, 30, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


def test_free_path_never_overwrites(tmp_path):
    first = config.free_path(tmp_path, "klick_2026-10-31_10-00-00.png")
    first.write_bytes(b"1")
    second = config.free_path(tmp_path, "klick_2026-10-31_10-00-00.png")
    second.write_bytes(b"2")
    assert second.name == "klick_2026-10-31_10-00-00_2.png" and first.read_bytes() == b"1"
    assert config.free_path(tmp_path, first.name).name == "klick_2026-10-31_10-00-00_3.png"


def test_prune_deletes_temporary_recordings_but_not_kept_ones(qapp, tmp_path):
    history = History(tmp_path / "h", run_ocr=False)
    history.media_dir.mkdir(parents=True)
    temp_clip = history.media_dir / "a.mp4"
    temp_clip.write_bytes(b"x")
    kept_clip = tmp_path / "b.mp4"
    kept_clip.write_bytes(b"x")
    history.add_media(temp_clip, "video", image(), temp=True)
    history.add_media(kept_clip, "video", image())
    history.add(image(), "copy")
    history.prune(1)
    assert not temp_clip.exists()  # ninguém mais acharia esse arquivo
    assert kept_clip.exists()  # este está na pasta do usuário
    history.close()


def test_failed_conversion_keeps_the_recording(qapp, tmp_path):
    for fmt, final in ((RecordFormat.GIF, "klick.mp4"), (RecordFormat.MP4, "klick.mp4")):
        recorder = Recorder()
        video = tmp_path / "raw.mp4"
        video.write_bytes(b"video")
        recorder._format, recorder._video = fmt, video
        recorder._target = tmp_path / f"klick.{fmt.value}"
        recorder._process = QProcess(recorder)
        done = []
        recorder.finished.connect(done.append)
        recorder._on_converted(1, QProcess.ExitStatus.NormalExit)
        assert done == [str(tmp_path / final)] and (tmp_path / final).read_bytes() == b"video"
        assert recorder.warning and not video.exists()
        (tmp_path / final).unlink()


def test_recognize_best_falls_back_when_precise_reads_nothing(monkeypatch):
    precise, windows = Future(), Future()
    monkeypatch.setattr(ocr, "precise_available", lambda: True)
    monkeypatch.setattr(ocr, "recognize_precise", lambda image: precise)
    monkeypatch.setattr(ocr, "recognize", lambda image, language=None: windows)
    out = ocr.recognize_best(QImage())
    precise.set_result(OcrResult(language="RapidOCR"))
    windows.set_result("lido pelo Windows")
    assert out.result(timeout=1) == "lido pelo Windows"


def test_reading_goes_to_gallery_even_if_precise_fails(qapp, monkeypatch):
    from test_ocr import wait_for
    from test_reader import fast_then_precise, page, result

    from klick.reader import ReaderWindow
    futures = fast_then_precise(monkeypatch)
    window = ReaderWindow(page())
    recognized = []
    window.recognized.connect(recognized.append)
    futures["fast"].set_result(result())
    assert wait_for(lambda: window.view.result is not None, 1000)
    futures["precise"].set_exception(RuntimeError("modelo ausente"))
    assert wait_for(lambda: len(recognized) == 1, 1000)
    assert recognized[0] is window.view.result
    window.close()


def test_cancelled_save_keeps_the_editor_open(qapp, tmp_path, monkeypatch):
    from test_app import make_app

    import klick.app
    klick_app = make_app(tmp_path)
    monkeypatch.setattr(klick.app, "save_image", lambda image: None)
    klick_app._open_editor_image(image())
    [editor] = klick_app._editors
    editor._finish(Action.SAVE)
    assert editor.isVisible() and klick_app._history.search() == []
    editor._finish(Action.COPY)
    assert not editor.isVisible()


def test_closing_settings_while_recording_a_shortcut_resumes_hotkeys(qapp):
    from klick.settings_ui import SettingsDialog
    dialog = SettingsDialog(None)
    paused = []
    dialog.hotkeysPaused.connect(paused.append)
    button = dialog.shortcuts["record"]
    button.listen()
    button.listen()  # segundo clique não abre outra escuta
    assert paused == [True] and button._recorder.active
    dialog.reject()
    assert paused == [True, False] and not button._recorder.active
    assert button.text() == config.hotkey_label(config.hotkeys()["record"])


def test_recording_without_history_goes_to_the_folder(qapp, tmp_path, monkeypatch):
    from test_app import make_app, selection

    from test_ocr import wait_for
    klick_app = make_app(tmp_path)
    monkeypatch.setattr(config, "history_enabled", lambda: False)
    monkeypatch.setattr(config, "save_dir", lambda: tmp_path / "Klick")
    started = []
    monkeypatch.setattr(klick_app._recorder, "start", lambda rect, fmt, folder, *a: started.append(folder))
    config.set_save_policy("recordings", "gallery")
    try:
        klick_app._start_recording(selection(), RecordFormat.MP4)
        assert wait_for(lambda: bool(started), 1000)
    finally:
        config.set_save_policy("recordings", "folder")
    # sem histórico, a galeria não guardaria o arquivo: vai para a pasta mesmo pedindo "só na galeria"
    assert started == [tmp_path / "Klick" / "Gravações"] and klick_app._recording[2] is False
    klick_app._close_indicator()
