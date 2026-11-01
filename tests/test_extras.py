from pathlib import Path

from PySide6.QtGui import QColor, QImage

from klick import lens
from klick.recorder import QUALITIES, encoder_args, gif_args, mux_args, record_args
from PySide6.QtCore import QRect


def test_quality_changes_encoder_and_gif():
    assert encoder_args("libx264", QUALITIES["high"])[-1] == "18"
    assert encoder_args("libopenh264", QUALITIES["low"])[-1] == "2M"
    vf = gif_args(Path("a.mp4"), Path("a.gif"), QUALITIES["low"])
    assert "fps=8," in vf[vf.index("-vf") + 1] and "640" in vf[vf.index("-vf") + 1]


def test_microphone_goes_into_ffmpeg():
    args = record_args(QRect(0, 0, 100, 100), Path("o.mp4"), 30, platform="win32", mic="Microfone (X)")
    assert args[args.index("dshow") + 4] == "audio=Microfone (X)"
    assert "aac" in args and args[-1] == "o.mp4"


def test_mux_mixes_system_sound_with_microphone():
    alone = mux_args(Path("v.mp4"), [Path("s.wav")], Path("o.mp4"), video_has_audio=False)
    assert "-filter_complex" not in alone and alone[alone.index("-map") + 3] == "1:a"
    both = mux_args(Path("v.mp4"), [Path("s.wav")], Path("o.mp4"), video_has_audio=True)
    assert "[0:a][1:a]amix=inputs=2" in both[both.index("-filter_complex") + 1]
    assert both[-1] == "o.mp4" and "copy" in both


def test_lens_page_carries_the_image(qapp):
    image = QImage(40, 30, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    page = lens.page(image)
    assert lens.UPLOAD in page and 'name="encoded_image"' in page
    assert lens.jpeg_base64(image) in page
