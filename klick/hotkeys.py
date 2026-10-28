"""Atalhos globais via pynput, entregues ao Qt como sinal."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class HotkeyListener(QObject):
    # Emitido na thread do pynput; como o QObject vive na thread principal,
    # a conexão vira queued e o slot roda no loop do Qt.
    triggered = Signal(str)

    def __init__(self, bindings: dict[str, str]):
        super().__init__()
        self._bindings = bindings
        self._listener = None

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception:  # noqa: BLE001 - pynput ausente ou sem backend (ex.: Wayland)
            log.warning("pynput indisponível; atalhos globais desativados", exc_info=True)
            return False
        handlers = {combo: (lambda name=name: self.triggered.emit(name)) for name, combo in self._bindings.items()}
        try:
            self._listener = keyboard.GlobalHotKeys(handlers)
            self._listener.start()
        except Exception:  # noqa: BLE001
            log.warning("Falha ao registrar atalhos globais %s", self._bindings, exc_info=True)
            self._listener = None
            return False
        return True

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
