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
    OCR = "ocr"  # OCR direto: o texto vai para o clipboard sem abrir nada
    READ = "read"  # abre a leitura, para escolher o trecho como no Google Lens
    EDIT = "edit"
    RECORD = "record"
    GIF = "gif"
    LENS = "lens"  # pesquisa a imagem no Google Lens, no navegador
    SQL = "sql"  # abre a janela de SQL (consulta ou grade de resultado)


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
    """Pergunta onde salvar (já sugerindo a pasta Prints e o nome) e grava. None se cancelado."""
    directory = config.folder("prints")
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
    return target


def store_image(image: QImage, kind: str = "prints") -> Path:
    """Grava direto na pasta do tipo, sem perguntar (usado pelo "salvar todo print")."""
    directory = config.folder(kind)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / config.default_filename()
    if not image.save(str(target)):
        raise OSError(f"Não foi possível salvar em {target}")
    return target


def store_text(text: str, ext: str = "txt") -> Path:
    """Grava o texto lido na pasta Leitura (.txt, ou .sql/.csv vindo da janela de SQL)."""
    directory = config.folder("reading")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / config.default_filename(ext=ext)
    target.write_text(text, encoding="utf-8")
    return target
