"""Gravação da área selecionada com ffmpeg.

No Windows usa gdigrab; no Linux, x11grab (não funciona em Wayland puro).
O GIF é gravado primeiro como MP4 e convertido depois com paleta otimizada,
o que deixa o arquivo bem menor e com cores melhores que gravar GIF direto.

Som: o microfone entra no próprio ffmpeg (dshow); o som do sistema é gravado à
parte (ver audio.py) e juntado ao vídeo quando a gravação para.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import re
import time
from dataclasses import dataclass
from enum import Enum
from functools import cache
from pathlib import Path

import shiboken6
from PySide6.QtCore import QObject, QProcess, QRect, QTimer, Signal

from klick import audio, config

log = logging.getLogger(__name__)

STOP_TIMEOUT_MS = 5000
GIF_FPS = 12
GIF_MAX_WIDTH = 960


@dataclass(frozen=True)
class Quality:
    label: str
    fps: int
    crf: int  # libx264: menor = melhor
    bitrate: str  # libopenh264
    q: int  # mpeg4: menor = melhor
    gif_fps: int
    gif_width: int
    hint: str


QUALITIES = {
    "low": Quality("Baixa", 15, 30, "2M", 6, 8, 640, "15 fps · arquivo pequeno"),
    "medium": Quality("Média", 30, 23, "4M", 3, GIF_FPS, GIF_MAX_WIDTH, "30 fps · equilibrada"),
    "high": Quality("Alta", 60, 18, "8M", 2, 15, 1280, "60 fps · nítida, arquivo maior"),
}


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
ENCODERS = ("libx264", "libopenh264", "mpeg4")


def encoder_args(name: str, quality: Quality = QUALITIES["medium"]) -> list[str]:
    if name == "libopenh264":
        return ["-c:v", "libopenh264", "-b:v", quality.bitrate]
    if name == "mpeg4":
        return ["-c:v", "mpeg4", "-q:v", str(quality.q)]
    return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", str(quality.crf)]


def _run(ffmpeg: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([ffmpeg, "-hide_banner", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


@cache
def video_encoder(ffmpeg: str) -> str:
    """Escolhe o melhor encoder que este ffmpeg tem (builds "free" vêm sem libx264)."""
    try:
        listing = _run(ffmpeg, "-encoders").stdout
    except (OSError, subprocess.SubprocessError):
        listing = ""
    available = {line.split()[1] for line in listing.splitlines() if len(line.split()) > 1}
    return next((name for name in ENCODERS if name in available), "libx264")


@cache
def microphone(ffmpeg: str) -> str | None:
    """Nome DirectShow do microfone (o padrão do Windows, se der para saber)."""
    if sys.platform != "win32":
        return None
    try:
        listing = _run(ffmpeg, "-list_devices", "true", "-f", "dshow", "-i", "dummy").stderr
    except (OSError, subprocess.SubprocessError):
        return None
    names = re.findall(r'"([^"]+)" \(audio\)', listing)
    if not names:
        return None
    try:
        import soundcard

        default = soundcard.default_microphone().name
        return next((n for n in names if default.startswith(n) or n.startswith(default)), names[0])
    except Exception:  # noqa: BLE001
        return names[0]


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
                encoder: list[str] | None = None, mic: str | None = None) -> list[str]:
    sound = ["-f", "dshow", "-audio_buffer_size", "50", "-i", f"audio={mic}"] if mic else []
    return [
        "-hide_banner", "-loglevel", "error", "-y",
        *grab_args(rect, fps, platform),
        *sound,
        *(encoder or encoder_args("libx264")), "-pix_fmt", "yuv420p",
        *(["-c:a", "aac", "-b:a", "160k"] if mic else []),
        "-movflags", "+faststart",
        str(output),
    ]


def gif_args(source: Path, output: Path, quality: Quality = QUALITIES["medium"]) -> list[str]:
    filters = (f"fps={quality.gif_fps},scale='min(iw,{quality.gif_width})':-1:flags=lanczos,"
               "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5")
    return ["-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vf", filters, "-loop", "0", str(output)]


def mux_args(video: Path, sounds: list[Path], output: Path, video_has_audio: bool) -> list[str]:
    """Junta o vídeo com os WAVs gravados à parte (misturando com o microfone, se houver)."""
    inputs = [arg for wav in sounds for arg in ("-i", str(wav))]
    streams = (["[0:a]"] if video_has_audio else []) + [f"[{i + 1}:a]" for i in range(len(sounds))]
    if len(streams) == 1:
        mapping = ["-map", "0:v", "-map", "1:a"]
    else:
        mix = f"{''.join(streams)}amix=inputs={len(streams)}:duration=longest:normalize=0[a]"
        mapping = ["-filter_complex", mix, "-map", "0:v", "-map", "[a]"]
    return ["-hide_banner", "-loglevel", "error", "-y", "-i", str(video), *inputs, *mapping,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(output)]


class Recorder(QObject):
    started = Signal()
    converting = Signal(str)  # gravação parou; o que está sendo feito ("Gerando GIF…")
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
        self._quality = QUALITIES["medium"]
        self._capture: audio.AudioCapture | None = None
        self._sounds: list[Path] = []
        self._mic = False
        self.last_duration = 0.0  # segundos da última gravação, medido ao parar
        self.warning = ""  # fonte de som que falhou na última gravação

    @property
    def busy(self) -> bool:
        return self._process is not None

    @property
    def recording(self) -> bool:
        return self.busy and not self._stopping

    def elapsed(self) -> float:
        return time.monotonic() - self._started_at if self.recording else 0.0

    def start(self, rect: QRect, fmt: RecordFormat, output_dir: Path, quality: str = "medium",
              sound: str = "none") -> None:
        """Grava `rect`. `sound` é "none", "system", "mic" ou "both" (GIF é sempre mudo)."""
        if self.busy:
            return
        ffmpeg = find_ffmpeg()
        if ffmpeg is None:
            self.failed.emit("ffmpeg não encontrado. Instale com: winget install ffmpeg")
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        self._format = fmt
        self._quality = QUALITIES.get(quality, QUALITIES["medium"])
        self.warning = ""
        sources = () if fmt is RecordFormat.GIF else audio.SOURCES.get(sound, ())
        mic = microphone(ffmpeg) if "mic" in sources else None
        if "mic" in sources and mic is None:
            self.warning = "Nenhum microfone encontrado"
        self._mic = mic is not None
        self._capture = audio.AudioCapture("system") if "system" in sources and audio.available() else None
        if "system" in sources and self._capture is None:
            self.warning = "Som do sistema indisponível"
        self._sounds = []
        self._target = output_dir / config.default_filename(ext=fmt.value)
        if fmt is RecordFormat.GIF or self._capture is not None:
            fd, tmp = tempfile.mkstemp(prefix="klick_", suffix=".mp4")
            os.close(fd)
            self._video = Path(tmp)
        else:
            self._video = self._target
        try:
            args = record_args(rect, self._video, self._quality.fps,
                               encoder=encoder_args(video_encoder(ffmpeg), self._quality), mic=mic)
        except RecorderError as exc:
            self.failed.emit(str(exc))
            return

        log.info("ffmpeg %s", " ".join(args))
        self._stopping = False
        self._process = self._spawn(ffmpeg, args, self._on_record_finished)
        if not self._process.waitForStarted(3000):
            self._fail(f"Não foi possível iniciar o ffmpeg: {self._process.errorString()}")
            return
        if self._capture is not None:
            self._capture.start()
        self._started_at = time.monotonic()
        self.started.emit()

    def stop(self) -> None:
        if not self.recording:
            return
        self.last_duration = self.elapsed()
        self._stopping = True
        if self._capture is not None:
            self._sounds = self._capture.stop()
            if self._capture.errors:
                self.warning = "Som do sistema não gravou"
            self._capture = None
        process = self._process
        process.write(b"q")  # o ffmpeg finaliza o arquivo direitinho ao receber "q"
        process.closeWriteChannel()
        # O processo pode já ter sido apagado (GIF ou som sendo gerados) quando o tempo acabar.
        QTimer.singleShot(STOP_TIMEOUT_MS, lambda: shiboken6.isValid(process)
                          and process.state() != QProcess.ProcessState.NotRunning and process.kill())

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
            self.converting.emit("Gerando GIF…")
            self._process.deleteLater()
            self._process = self._spawn(find_ffmpeg(), gif_args(self._video, self._target, self._quality),
                                        self._on_converted)
            return
        if self._video != self._target:
            if not self._sounds:  # o som não gravou nada: fica só o vídeo
                shutil.move(str(self._video), str(self._target))
                self._done()
                return
            self.converting.emit("Juntando o som…")
            self._process.deleteLater()
            self._process = self._spawn(find_ffmpeg(), mux_args(self._video, self._sounds, self._target, self._mic),
                                        self._on_converted)
            return
        self._done()

    def _on_converted(self, code: int, status: QProcess.ExitStatus) -> None:
        error = self._stderr()
        self._video.unlink(missing_ok=True)
        self._drop_sounds()
        if code != 0 or not self._target.exists():
            what = "o GIF" if self._format is RecordFormat.GIF else "o vídeo com som"
            self._fail(f"Falha ao gerar {what}: {error or f'código {code}'}")
            return
        self._done()

    def _drop_sounds(self) -> None:
        for wav in self._sounds:
            wav.unlink(missing_ok=True)
        self._sounds = []

    def _done(self) -> None:
        target = self._target
        self._reset()
        self.finished.emit(str(target))

    def _fail(self, message: str) -> None:
        if self._video and self._video != self._target:
            self._video.unlink(missing_ok=True)
        if self._capture is not None:
            self._sounds = self._capture.stop()
            self._capture = None
        self._drop_sounds()
        self._reset()
        self.failed.emit(message)

    def _reset(self) -> None:
        if self._process is not None:
            self._process.deleteLater()
        self._process = None
        self._stopping = False
