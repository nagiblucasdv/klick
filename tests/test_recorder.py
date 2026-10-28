import shutil
import time

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from klick import recorder
from klick.recorder import Recorder, RecordFormat, RecorderError, even_rect, gif_args, grab_args, record_args


def wait_for(predicate, timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_even_rect_rounds_down_odd_sizes():
    assert even_rect(QRect(5, 7, 101, 51)) == QRect(5, 7, 100, 50)


def test_gdigrab_uses_physical_offsets():
    args = grab_args(QRect(-1920, 40, 641, 480), 30, platform="win32")
    assert args == ["-f", "gdigrab", "-framerate", "30", "-offset_x", "-1920", "-offset_y", "40",
                    "-video_size", "640x480", "-draw_mouse", "1", "-i", "desktop"]


def test_x11grab_args():
    args = grab_args(QRect(10, 20, 100, 50), 24, platform="linux", display=":0")
    assert args[-2:] == ["-i", ":0+10,20"]
    assert "100x50" in args


def test_linux_without_display_fails():
    with pytest.raises(RecorderError):
        grab_args(QRect(0, 0, 10, 10), 30, platform="linux", display="")


def test_record_args_end_with_output(tmp_path):
    out = tmp_path / "a.mp4"
    args = record_args(QRect(0, 0, 100, 100), out, 30, platform="win32")
    assert args[-1] == str(out)
    assert "libx264" in args and "yuv420p" in args


def test_gif_args_use_palette(tmp_path):
    args = gif_args(tmp_path / "a.mp4", tmp_path / "a.gif")
    assert any("palettegen" in a and "paletteuse" in a for a in args)


def test_missing_ffmpeg_reports_failure(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(recorder, "find_ffmpeg", lambda: None)
    rec = Recorder()
    errors = []
    rec.failed.connect(errors.append)
    rec.start(QRect(0, 0, 100, 100), RecordFormat.MP4, tmp_path)
    assert errors and "ffmpeg" in errors[0]
    assert not rec.busy


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg não instalado")


def fake_screen(rect, fps, platform=None, display=None):
    # Fonte sintética no lugar da tela: testa o fluxo real do ffmpeg sem precisar de display.
    return ["-re", "-f", "lavfi", "-i", f"testsrc=size={rect.width()}x{rect.height()}:rate={fps}"]


@needs_ffmpeg
@pytest.mark.parametrize("fmt", [RecordFormat.MP4, RecordFormat.GIF])
def test_record_and_stop(qapp, monkeypatch, tmp_path, fmt):
    monkeypatch.setattr(recorder, "grab_args", fake_screen)
    rec = Recorder()
    done, errors = [], []
    rec.finished.connect(done.append)
    rec.failed.connect(errors.append)
    rec.start(QRect(0, 0, 161, 121), fmt, tmp_path)
    assert rec.recording, errors
    wait_for(lambda: False, 800)  # grava ~0,8 s
    rec.stop()
    assert wait_for(lambda: done or errors, 15000)
    assert not errors
    path = tmp_path / done[0].rsplit("/", 1)[-1]
    assert path.suffix == f".{fmt.value}"
    assert path.stat().st_size > 0
    assert not rec.busy
    if fmt is RecordFormat.GIF:
        assert path.read_bytes()[:6] == b"GIF89a"


@needs_ffmpeg
def test_ffmpeg_crash_is_reported(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(recorder, "grab_args", lambda *a, **k: ["-f", "lavfi", "-i", "nao_existe"])
    rec = Recorder()
    errors = []
    rec.failed.connect(errors.append)
    rec.start(QRect(0, 0, 100, 100), RecordFormat.MP4, tmp_path)
    assert wait_for(lambda: bool(errors), 10000)
    assert "parou sozinho" in errors[0]
    assert not rec.busy
