"""Preferências persistidas via QSettings (registro no Windows)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

DEFAULT_HOTKEYS = {
    "capture": "<print_screen>",
    # Reservado para o próximo passo do plano (OCR direto).
    # "ocr": "<ctrl>+<shift>+t",
}


def _settings() -> QSettings:
    return QSettings("Klick", "Klick")


def default_save_dir() -> Path:
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return Path(pictures or Path.home()) / "Klick"


def save_dir() -> Path:
    value = _settings().value("save_dir")
    return Path(value) if value else default_save_dir()


def set_save_dir(path: Path) -> None:
    _settings().setValue("save_dir", str(path))


def hotkeys() -> dict[str, str]:
    settings = _settings()
    return {name: str(settings.value(f"hotkeys/{name}", combo)) for name, combo in DEFAULT_HOTKEYS.items()}


def default_filename(now: datetime | None = None) -> str:
    return f"klick_{(now or datetime.now()):%Y-%m-%d_%H-%M-%S}.png"
