from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

from klick.actions import Action
from klick.app import KlickApp
from klick.capture import Selection
from klick.history import History


def selection() -> Selection:
    image = QImage(40, 20, QImage.Format.Format_RGB32)
    image.fill(QColor("green"))
    return Selection(image, QRect(0, 0, 40, 20), QRect(0, 0, 40, 20), QGuiApplication.primaryScreen())


def make_app(tmp_path) -> KlickApp:
    return KlickApp(QApplication.instance(), history=History(tmp_path, run_ocr=False))


def test_copy_goes_to_clipboard_and_history(qapp, tmp_path):
    klick = make_app(tmp_path)
    klick._on_finished(Action.COPY, selection())
    assert QGuiApplication.clipboard().image().size() == selection().image.size()
    assert [e.source for e in klick._history.search()] == ["copy"]


def test_edit_opens_editor_and_copy_is_recorded_as_edit(qapp, tmp_path):
    klick = make_app(tmp_path)
    klick._on_finished(Action.EDIT, selection())
    [editor] = klick._editors
    editor._finish(Action.COPY)
    assert [e.source for e in klick._history.search()] == ["edit"]


def test_record_without_ffmpeg_warns(qapp, tmp_path, monkeypatch):
    from klick import recorder

    monkeypatch.setattr(recorder, "find_ffmpeg", lambda: None)
    klick = make_app(tmp_path)
    warnings = []
    monkeypatch.setattr(klick, "_warn", warnings.append)
    klick._start_recording(selection(), recorder.RecordFormat.MP4)
    from test_ocr import wait_for

    assert wait_for(lambda: bool(warnings), 2000)
    assert klick._indicator is None
