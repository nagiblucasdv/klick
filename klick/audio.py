"""Som do computador na gravação (loopback do WASAPI).

O ffmpeg do Windows não grava o som do sistema sem "Mixagem estéreo", então ele é gravado
à parte em WAV, numa thread, e juntado ao vídeo quando a gravação para (ver Recorder).
O microfone não passa por aqui: entra direto no ffmpeg (dshow).
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


class AudioCapture:
    """Grava o som do computador num WAV temporário até `stop()`."""

    def __init__(self):
        self.errors: list[str] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        fd, name = tempfile.mkstemp(prefix="klick_system_", suffix=".wav")
        os.close(fd)
        self._path = Path(name)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> list[Path]:
        """Para e devolve o WAV, se gravou alguma coisa (senão apaga o arquivo vazio)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        if self._path.exists() and self._path.stat().st_size > 44:  # 44 bytes = só o cabeçalho
            return [self._path]
        self._path.unlink(missing_ok=True)
        return []

    def _run(self) -> None:
        try:
            import numpy as np
            import soundcard as sc

            device = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
            with wave.open(str(self._path), "wb") as out, device.recorder(samplerate=RATE, channels=2) as rec:
                out.setnchannels(2)
                out.setsampwidth(2)
                out.setframerate(RATE)
                while not self._stop.is_set():
                    data = rec.record(numframes=CHUNK)
                    out.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())
        except Exception as exc:  # noqa: BLE001 - a gravação segue sem o som do computador
            log.warning("Som do computador falhou", exc_info=exc)
            self.errors.append("som do computador")
