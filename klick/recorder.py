"""Gravação da área selecionada com ffmpeg.

No Windows usa gdigrab; no Linux, x11grab (não funciona em Wayland puro).
O GIF é gravado primeiro como MP4 e convertido depois com paleta otimizada,
o que deixa o arquivo bem menor e com cores melhores que gravar GIF direto.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from enum import Enum
from functools import cache
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QRect, QTimer, Signal

from klick import config

log = logging.getLogger(__name__)

STOP_TIMEOUT_MS = 5000
GIF_FPS = 12
GIF_MAX_WIDTH = 960


class RecordFormat(str, Enum):
    MP4 = "mp4"
    GIF = "gif"


class RecorderError(RuntimeError):
    pass


def find_ffmpeg() -> str | None:
    return config.ffmpeg_path() or bundled_ffmpeg() or shutil.which("ffmpeg")


def bundled_ffmpeg() -> str | None:
    """ffmpeg que o instalador coloca ao lado do Klick.exe."""
    if not getattr(sys, "frozen", False):
        return None
    candidate = Path(sys.executable).with_name("ffmpeg.exe")
    return str(candidate) if candidate.is_file() else None


# Em ordem de preferência; hardware (nvenc/amf/qsv) fica de fora porque falha em
# máquinas sem a GPU certa mesmo quando aparece na lista.
ENCODERS = {
    "libx264": ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"],
    "libopenh264": ["-c:v", "libopenh264", "-b:v", "4M"],
    "mpeg4": ["-c:v", "mpeg4", "-q:v", "3"],
}


@cache
def video_encoder(ffmpeg: str) -> list[str]:
    """Escolhe o melhor encoder que este ffmpeg tem (builds "free" vêm sem libx264)."""
    try:
        listing = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True,
                                 timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        listing = ""
    available = {line.split()[1] for line in listing.splitlines() if len(line.split()) > 1}
    for name, args in ENCODERS.items():
        if name in available:
            return args
    return ENCODERS["libx264"]


def even_rect(rect: QRect) -> QRect:
    """O H.264 com yuv420p exige largura e altura pares."""
    return QRect(rect.x(), rect.y(), max(2, rect.width() - rect.width() % 2), max(2, rect.height() - rect.height() % 2))


def grab_args(rect: QRect, fps: int, platform: str = sys.platform, display: str | None = None) -> list[str]:
    rect = even_rect(rect)
    size = f"{rect.width()}x{rect.height()}"
    if platform == "win32":
        return ["-f", "gdigrab", "-framerate", str(fps), "-offset_x", str(rect.x()), "-offset_y", str(rect.y()),
                "-video_size", size, "-draw_mouse", "1", "-i", "desktop"]
    if platform.startswith("linux"):
        display = display if display is not None else os.environ.get("DISPLAY")
        if not display:
            raise RecorderError("Gravação no Linux precisa de X11 (variável DISPLAY não definida).")
        return ["-f", "x11grab", "-framerate", str(fps), "-video_size", size, "-draw_mouse", "1",
                "-i", f"{display}+{rect.x()},{rect.y()}"]
    raise RecorderError(f"Gravação ainda não suportada em {platform}.")


def record_args(rect: QRect, output: Path, fps: int, platform: str = sys.platform,
                encoder: list[str] = ENCODERS["libx264"]) -> list[str]:
    return [
        "-hide_banner", "-loglevel", "error", "-y",
        *grab_args(rect, fps, platform),
        *encoder, "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ]


def gif_args(source: Path, output: Path) -> list[str]:
    filters = (f"fps={GIF_FPS},scale='min(iw,{GIF_MAX_WIDTH})':-1:flags=lanczos,"
               "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5")
    return ["-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vf", filters, "-loop", "0", str(output)]


class Recorder(QObject):
    started = Signal()
    converting = Signal()  # gravação parou, GIF sendo gerado
    finished = Signal(str)  # caminho do arquivo final
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._process: QProcess | None = None
        self._format = RecordFormat.MP4
        self._video: Path | None = None
        self._target: Path | None = None
        self._stopping = False
        self._started_at = 0.0

    @property
    def busy(self) -> bool:
        return self._process is not None

    @property
    def recording(self) -> bool:
        return self.busy and not self._stopping

    def elapsed(self) -> float:
        return time.monotonic() - self._started_at if self.recording else 0.0

    def start(self, rect: QRect, fmt: RecordFormat, output_dir: Path) -> None:
        if self.busy:
            return
        ffmpeg = find_ffmpeg()
        if ffmpeg is None:
            self.failed.emit("ffmpeg não encontrado. Instale com: winget install ffmpeg")
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        self._format = fmt
        self._target = output_dir / config.default_filename(ext=fmt.value)
        if fmt is RecordFormat.GIF:
            fd, tmp = tempfile.mkstemp(prefix="klick_", suffix=".mp4")
            os.close(fd)
            self._video = Path(tmp)
        else:
            self._video = self._target
        try:
            args = record_args(rect, self._video, config.record_fps(), encoder=video_encoder(ffmpeg))
        except RecorderError as exc:
            self.failed.emit(str(exc))
            return

        log.info("ffmpeg %s", " ".join(args))
        self._stopping = False
        self._process = self._spawn(ffmpeg, args, self._on_record_finished)
        if not self._process.waitForStarted(3000):
            self._fail(f"Não foi possível iniciar o ffmpeg: {self._process.errorString()}")
            return
        self._started_at = time.monotonic()
        self.started.emit()

    def stop(self) -> None:
        if not self.recording:
            return
        self._stopping = True
        process = self._process
        process.write(b"q")  # o ffmpeg finaliza o arquivo direitinho ao receber "q"
        process.closeWriteChannel()
        QTimer.singleShot(STOP_TIMEOUT_MS, lambda: process.state() != QProcess.ProcessState.NotRunning
                          and process.kill())

    # --- internos ----------------------------------------------------------

    def _spawn(self, program: str, args: list[str], on_finished) -> QProcess:
        process = QProcess(self)
        process.setProgram(program)
        process.setArguments(args)
        process.finished.connect(on_finished)
        process.start()
        return process

    def _stderr(self) -> str:
        return bytes(self._process.readAllStandardError()).decode(errors="replace").strip()

    def _on_record_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if not self._stopping:
            self._fail(f"O ffmpeg parou sozinho: {self._stderr() or f'código {code}'}")
            return
        if not self._video or not self._video.exists() or self._video.stat().st_size == 0:
            self._fail(f"A gravação não gerou arquivo. {self._stderr()}")
            return
        if self._format is RecordFormat.GIF:
            self.converting.emit()
            self._process.deleteLater()
            self._process = self._spawn(find_ffmpeg(), gif_args(self._video, self._target), self._on_gif_finished)
            return
        self._done()

    def _on_gif_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        error = self._stderr()
        self._video.unlink(missing_ok=True)
        if code != 0 or not self._target.exists():
            self._fail(f"Falha ao gerar o GIF: {error or f'código {code}'}")
            return
        self._done()

    def _done(self) -> None:
        target = self._target
        self._reset()
        self.finished.emit(str(target))

    def _fail(self, message: str) -> None:
        if self._format is RecordFormat.GIF and self._video:
            self._video.unlink(missing_ok=True)
        self._reset()
        self.failed.emit(message)

    def _reset(self) -> None:
        if self._process is not None:
            self._process.deleteLater()
        self._process = None
        self._stopping = False
