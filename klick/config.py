"""Preferências persistidas via QSettings (registro no Windows)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

DEFAULT_HOTKEYS = {
    "capture": "<print_screen>",
    "ocr": "<ctrl>+<shift>+t",  # OCR direto: seleciona e o texto já vai para o clipboard
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


def ocr_language() -> str | None:
    """Tag BCP-47 (ex.: "pt-BR"). None usa os idiomas do perfil do Windows."""
    value = _settings().value("ocr/language")
    return str(value) if value else None


def default_filename(now: datetime | None = None) -> str:
    return f"klick_{(now or datetime.now()):%Y-%m-%d_%H-%M-%S}.png"
