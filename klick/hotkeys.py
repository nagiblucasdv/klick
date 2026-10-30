"""Atalhos globais via pynput, entregues ao Qt como sinal, e a gravação de um atalho novo."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

MODIFIERS = {"ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl", "shift": "shift", "shift_l": "shift",
             "shift_r": "shift", "alt": "alt", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt", "cmd": "cmd",
             "cmd_l": "cmd", "cmd_r": "cmd"}
ORDER = ["ctrl", "shift", "alt", "cmd"]


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

    def restart(self, bindings: dict[str, str]) -> bool:
        self.stop()
        self._bindings = bindings
        return self.start()


def key_name(key) -> str | None:
    """Tecla do pynput no formato dos atalhos: "<ctrl>", "<f7>", "t" ou "<118>" (código da tecla)."""
    name = getattr(key, "name", None)
    if name:  # keyboard.Key
        return f"<{MODIFIERS.get(name, name)}>"
    vk = getattr(key, "vk", None)
    if vk is not None and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
        return chr(vk).lower()  # letras e números pelo código: com Ctrl o char vem como controle
    char = getattr(key, "char", None)
    if char and char.isprintable():
        return char.lower()
    return f"<{vk}>" if vk is not None else None


def combo(keys: list[str]) -> str:
    """Junta as teclas com os modificadores primeiro: ["t", "<shift>", "<ctrl>"] -> "<ctrl>+<shift>+t"."""
    mods = [f"<{m}>" for m in ORDER if f"<{m}>" in keys]
    rest = [k for k in keys if k not in mods]
    return "+".join(mods + rest)


class KeyRecorder(QObject):
    """Escuta o teclado inteiro até você soltar tudo e devolve a combinação apertada.

    Serve para teclas que o Qt não vê, como a que o FN gera em notebooks. Esc sozinho cancela.
    """

    recorded = Signal(str)  # "" quando cancelado

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._listener = None
        self._down: list[str] = []
        self._pressed: list[str] = []

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception:  # noqa: BLE001
            return False
        self._down, self._pressed = [], []
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()
        return True

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        name = key_name(key)
        if name and name not in self._down:
            self._down.append(name)
            if name not in self._pressed:
                self._pressed.append(name)

    def _on_release(self, key):
        name = key_name(key)
        if name in self._down:
            self._down.remove(name)
        if self._down or not self._pressed:
            return None
        keys, self._pressed = self._pressed, []
        if keys == ["<esc>"]:
            self.recorded.emit("")
            return False
        if all(k.strip("<>") in ORDER for k in keys):
            return None  # só modificadores: espera a tecla de verdade
        self.recorded.emit(combo(keys))
        return False  # para o listener
