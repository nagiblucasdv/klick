"""Som da gravação: o que toca no computador (loopback do WASAPI) e/ou o microfone.

O ffmpeg do Windows não grava o som do sistema sem "Mixagem estéreo", então o áudio
é gravado à parte em WAV, numa thread por fonte, e juntado ao vídeo quando a
gravação para (ver Recorder).
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import wave
from pathlib import Path

log = logging.getLogger(__name__)

RATE = 48000
CHUNK = RATE // 10  # 100 ms por leitura

# Fontes de cada opção de som da gravação.
SOURCES = {"none": (), "system": ("system",), "mic": ("mic",), "both": ("system", "mic")}


def available() -> bool:
    try:
        import soundcard  # noqa: F401
    except Exception:  # noqa: BLE001 - sem placa de som ou sem a biblioteca: grava sem áudio
        return False
    return True


def _device(source: str):
    import soundcard as sc

    if source == "system":
        return sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True), 2
    return sc.default_microphone(), 1


class AudioCapture:
    """Grava cada fonte num WAV temporário até `stop()`."""

    def __init__(self, audio: str):
        self.sources = SOURCES.get(audio, ())
        self.files: list[Path] = []
        self.errors: list[str] = []
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for source in self.sources:
            fd, name = tempfile.mkstemp(prefix=f"klick_{source}_", suffix=".wav")
            os.close(fd)
            path = Path(name)
            thread = threading.Thread(target=self._run, args=(source, path), daemon=True)
            self._threads.append(thread)
            thread.start()

    def stop(self) -> list[Path]:
        """Para e devolve os WAVs que gravaram alguma coisa."""
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=3)
        return [f for f in self.files if f.exists() and f.stat().st_size > 44]

    def _run(self, source: str, path: Path) -> None:
        try:
            import numpy as np

            device, channels = _device(source)
            with wave.open(str(path), "wb") as out, device.recorder(samplerate=RATE, channels=channels) as rec:
                out.setnchannels(channels)
                out.setsampwidth(2)
                out.setframerate(RATE)
                self.files.append(path)
                while not self._stop.is_set():
                    data = rec.record(numframes=CHUNK)
                    out.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())
        except Exception as exc:  # noqa: BLE001 - a gravação segue sem esta fonte
            log.warning("Áudio (%s) falhou", source, exc_info=exc)
            self.errors.append("microfone" if source == "mic" else "som do sistema")
