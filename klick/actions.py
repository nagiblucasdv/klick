"""O que fazer com a imagem depois da seleção."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QFileDialog

from klick import config


class Action(str, Enum):
    COPY = "copy"
    SAVE = "save"
    OCR = "ocr"
    EDIT = "edit"
    RECORD = "record"
    GIF = "gif"


def copy_image(image: QImage) -> None:
    QGuiApplication.clipboard().setImage(image)


def copy_text(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def copy_file(path: Path) -> None:
    """Copia o arquivo em si (como Ctrl+C no Explorer), para colar direto em chat ou ticket."""
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    mime.setText(str(path))
    QGuiApplication.clipboard().setMimeData(mime)


def save_image(image: QImage) -> Path | None:
    """Pergunta onde salvar (já sugerindo pasta e nome) e grava. None se cancelado."""
    directory = config.save_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path, _ = QFileDialog.getSaveFileName(
        None,
        "Salvar captura",
        str(directory / config.default_filename()),
        "PNG (*.png);;JPEG (*.jpg *.jpeg)",
    )
    if not path:
        return None
    target = Path(path)
    if not target.suffix:
        target = target.with_suffix(".png")
    if not image.save(str(target)):
        raise OSError(f"Não foi possível salvar em {target}")
    config.set_save_dir(target.parent)
    return target
