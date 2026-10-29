"""Preferências persistidas via QSettings (registro no Windows)."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

DEFAULT_HOTKEYS = {
    "capture": "<print_screen>",
    "ocr": "<ctrl>+<shift>+t",  # OCR direto: seleciona e o texto já vai para o clipboard
    "record": "<ctrl>+<shift>+r",  # inicia a gravação; apertar de novo para
}


def _settings() -> QSettings:
    # KLICK_SETTINGS aponta para um .ini (usado pelos testes para não tocar nas preferências reais).
    path = os.environ.get("KLICK_SETTINGS")
    if path:
        return QSettings(path, QSettings.Format.IniFormat)
    return QSettings("Klick", "Klick")


def _bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes")
    return bool(value)


# Uma pasta por tipo de conteúdo, dentro da pasta do Klick (Imagens/Klick).
FOLDERS = {"prints": "Prints", "recordings": "Gravações", "gifs": "GIFs", "reading": "Leitura"}

# Opções que o usuário liga e desliga nas configurações da galeria.
OPTIONS = {
    "loupe": True,  # lupa de pixels ao selecionar
    "guides": True,  # linhas dos terços enquanto arrasta
    "toasts": True,  # aviso com ações depois de copiar
    "autosave": False,  # todo print copiado também vai para a pasta Prints
    "precise_ocr": True,  # RapidOCR refina a leitura do Windows
    "record_ask": True,  # pergunta som e qualidade antes de gravar
    "addon_sql": True,  # extra: SQL e tabelas na leitura
}
AUDIO = ("none", "system", "mic", "both")
QUALITY = ("low", "medium", "high")


def option(name: str) -> bool:
    return _bool(_settings().value(f"options/{name}"), OPTIONS[name])


def set_option(name: str, value: bool) -> None:
    _settings().setValue(f"options/{name}", value)


def record_audio() -> str:
    value = str(_settings().value("record/audio", "none"))
    return value if value in AUDIO else "none"


def set_record_audio(value: str) -> None:
    _settings().setValue("record/audio", value)


def record_quality() -> str:
    value = str(_settings().value("record/quality", "medium"))
    return value if value in QUALITY else "medium"


def set_record_quality(value: str) -> None:
    _settings().setValue("record/quality", value)


def default_save_dir() -> Path:
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return Path(pictures or Path.home()) / "Klick"


def save_dir() -> Path:
    value = _settings().value("save_dir")
    return Path(value) if value else default_save_dir()


def set_save_dir(path: Path) -> None:
    _settings().setValue("save_dir", str(path))


def folder(kind: str) -> Path:
    """Pasta de um tipo de conteúdo ("prints", "recordings", "gifs" ou "reading")."""
    return save_dir() / FOLDERS[kind]


def hotkeys() -> dict[str, str]:
    settings = _settings()
    return {name: str(settings.value(f"hotkeys/{name}", combo)) for name, combo in DEFAULT_HOTKEYS.items()}


def ocr_language() -> str | None:
    """Tag BCP-47 (ex.: "pt-BR"). None usa os idiomas do perfil do Windows."""
    value = _settings().value("ocr/language")
    return str(value) if value else None


def ffmpeg_path() -> str | None:
    value = _settings().value("record/ffmpeg")
    return str(value) if value else None


def history_enabled() -> bool:
    return _bool(_settings().value("history/enabled"), True)


def set_history_enabled(enabled: bool) -> None:
    _settings().setValue("history/enabled", enabled)


def history_max_items() -> int:
    return int(_settings().value("history/max_items", 1000))


def history_dir() -> Path:
    value = os.environ.get("KLICK_HISTORY_DIR")
    if value:
        return Path(value)
    data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    return Path(data or Path.home()) / "Klick" / "history"


def default_filename(now: datetime | None = None, ext: str = "png") -> str:
    return f"klick_{(now or datetime.now()):%Y-%m-%d_%H-%M-%S}.{ext}"
