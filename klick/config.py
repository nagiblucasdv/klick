"""Preferências persistidas via QSettings (registro no Windows)."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

# Atalhos no formato do pynput. O print (PrtSc) só faz imagem; vídeo e GIF ficam no atalho de gravar.
DEFAULT_HOTKEYS = {
    "capture": "<print_screen>",
    "record": "<f7>",  # escolhe a área e grava vídeo ou GIF; apertar de novo para
    "ocr": "<ctrl>+<shift>+t",  # OCR direto: seleciona e o texto já vai para o clipboard
}
HOTKEY_NAMES = {"capture": "Print", "record": "Gravar vídeo ou GIF", "ocr": "Ler texto direto"}
KEY_LABELS = {"print_screen": "PrtSc", "ctrl": "Ctrl", "ctrl_l": "Ctrl", "ctrl_r": "Ctrl", "shift": "Shift",
              "shift_l": "Shift", "shift_r": "Shift", "alt": "Alt", "alt_l": "Alt", "alt_r": "Alt Gr",
              "alt_gr": "Alt Gr", "cmd": "Win", "cmd_l": "Win", "cmd_r": "Win", "page_up": "PgUp",
              "page_down": "PgDn", "insert": "Ins", "delete": "Del", "pause": "Pause", "scroll_lock": "ScrLk"}


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
    "precise_ocr": True,  # RapidOCR refina a leitura do Windows
    "record_ask": True,  # pergunta som e qualidade antes de gravar
    "addon_sql": True,  # extra: SQL e tabelas na leitura
}
AUDIO = ("none", "system", "mic", "both")
QUALITY = ("low", "medium", "high")

# Onde cada tipo fica: "folder" grava na pasta do tipo na hora; "gallery" fica só na galeria
# (temporário) até você mandar guardar, e some depois de TEMP_DAYS.
SAVE_DEFAULTS = {"prints": "gallery", "reading": "gallery", "recordings": "folder", "gifs": "folder"}
TEMP_DAYS = (1, 7, 30, 0)  # 0 = nunca apaga


def option(name: str) -> bool:
    return _bool(_settings().value(f"options/{name}"), OPTIONS[name])


def set_option(name: str, value: bool) -> None:
    _settings().setValue(f"options/{name}", value)


def record_audio() -> str:
    value = str(_settings().value("record/audio", "none"))
    return value if value in AUDIO else "none"


def set_record_audio(value: str) -> None:
    _settings().setValue("record/audio", value)


def record_format() -> str:
    value = str(_settings().value("record/format", "video"))
    return value if value in ("video", "gif") else "video"


def set_record_format(value: str) -> None:
    _settings().setValue("record/format", value)


def record_quality() -> str:
    value = str(_settings().value("record/quality", "medium"))
    return value if value in QUALITY else "medium"


def set_record_quality(value: str) -> None:
    _settings().setValue("record/quality", value)


def save_policy(kind: str) -> str:
    """ "folder" ou "gallery" para "prints", "reading", "recordings" ou "gifs"."""
    settings = _settings()
    value = settings.value(f"save/{kind}")
    if value is None and kind == "prints" and _bool(settings.value("options/autosave"), False):
        return "folder"  # quem ligou "salvar todo print" na versão anterior
    return str(value) if value in ("folder", "gallery") else SAVE_DEFAULTS[kind]


def set_save_policy(kind: str, value: str) -> None:
    _settings().setValue(f"save/{kind}", value)


def temp_days() -> int:
    """Dias que o que está só na galeria fica antes de ser apagado (0 = nunca)."""
    try:
        value = int(_settings().value("save/temp_days", 7))
    except (TypeError, ValueError):
        return 7
    return value if value in TEMP_DAYS else 7


def set_temp_days(days: int) -> None:
    _settings().setValue("save/temp_days", days)


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


def set_hotkey(name: str, combo: str) -> None:
    _settings().setValue(f"hotkeys/{name}", combo)


def hotkey_label(combo: str) -> str:
    """ "<ctrl>+<shift>+t" -> "Ctrl+Shift+T"; "<print_screen>" -> "PrtSc"; "<118>" (código) -> "Tecla 118"."""
    parts = []
    for part in combo.split("+"):
        key = part.strip("<>")
        if key.isdigit():
            parts.append(f"Tecla {key}")
        elif key in KEY_LABELS:
            parts.append(KEY_LABELS[key])
        else:
            parts.append(key.upper() if len(key) <= 3 else key.replace("_", " ").title())
    return "+".join(parts)


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
