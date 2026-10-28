"""Histórico pesquisável: cada captura vira uma linha no SQLite com o texto do OCR.

A busca usa FTS5 com remove_diacritics, então "erro" acha "Erro" e "atencao"
acha "Atenção". O OCR das capturas roda em segundo plano depois de salvar.
"""

from __future__ import annotations

import logging
import sqlite3
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage

from klick import config, ocr

log = logging.getLogger(__name__)

THUMB_WIDTH = 320

SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT ''
);
CREATE VIRTUAL TABLE IF NOT EXISTS captures_fts USING fts5(
    text, content='captures', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS captures_ai AFTER INSERT ON captures BEGIN
    INSERT INTO captures_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS captures_ad AFTER DELETE ON captures BEGIN
    INSERT INTO captures_fts(captures_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS captures_au AFTER UPDATE OF text ON captures BEGIN
    INSERT INTO captures_fts(captures_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO captures_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


@dataclass
class Entry:
    id: int
    created_at: datetime
    source: str
    width: int
    height: int
    text: str
    image_path: Path
    thumb_path: Path


def fts_query(text: str) -> str:
    """Transforma o que o usuário digitou numa busca FTS5 segura: todos os termos, com prefixo."""
    terms = [t.replace('"', '""') for t in text.split()]
    return " ".join(f'"{t}"*' for t in terms)


class History(QObject):
    changed = Signal()
    _ocrDone = Signal(int, str)  # vem da thread do OCR

    def __init__(self, root: Path | None = None, run_ocr: bool = True):
        super().__init__()
        self.root = root or config.history_dir()
        self.images = self.root / "images"
        self.images.mkdir(parents=True, exist_ok=True)
        self._run_ocr = run_ocr
        self._db = sqlite3.connect(self.root / "history.db")
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._ocrDone.connect(self.set_text)

    def close(self) -> None:
        self._db.close()

    @property
    def enabled(self) -> bool:
        return config.history_enabled()

    def add(self, image: QImage, source: str, text: str | None = None) -> int | None:
        """Guarda a captura. Sem `text`, roda o OCR em segundo plano para indexar."""
        if not self.enabled or image.isNull():
            return None
        with self._db:
            cur = self._db.execute(
                "INSERT INTO captures (created_at, source, width, height, text) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), source, image.width(), image.height(), text or ""),
            )
        entry_id = cur.lastrowid
        image.save(str(self._image_path(entry_id)), "PNG")
        thumb = image.scaledToWidth(min(THUMB_WIDTH, image.width()), Qt.TransformationMode.SmoothTransformation)
        thumb.save(str(self._thumb_path(entry_id)), "JPG", 85)
        if text is None and self._run_ocr:
            ocr.recognize(image, config.ocr_language()).add_done_callback(
                lambda future: self._emit_ocr(entry_id, future))
        self.prune(config.history_max_items())
        self.changed.emit()
        return entry_id

    def set_text(self, entry_id: int, text: str) -> None:
        with self._db:
            self._db.execute("UPDATE captures SET text = ? WHERE id = ?", (text, entry_id))
        self.changed.emit()

    def search(self, query: str = "", limit: int = 200) -> list[Entry]:
        match = fts_query(query)
        if match:
            rows = self._db.execute(
                "SELECT c.* FROM captures c JOIN captures_fts f ON f.rowid = c.id "
                "WHERE captures_fts MATCH ? ORDER BY c.id DESC LIMIT ?", (match, limit))
        else:
            rows = self._db.execute("SELECT * FROM captures ORDER BY id DESC LIMIT ?", (limit,))
        return [self._entry(row) for row in rows]

    def get(self, entry_id: int) -> Entry | None:
        row = self._db.execute("SELECT * FROM captures WHERE id = ?", (entry_id,)).fetchone()
        return self._entry(row) if row else None

    def delete(self, entry_id: int) -> None:
        with self._db:
            self._db.execute("DELETE FROM captures WHERE id = ?", (entry_id,))
        self._image_path(entry_id).unlink(missing_ok=True)
        self._thumb_path(entry_id).unlink(missing_ok=True)
        self.changed.emit()

    def prune(self, keep: int) -> None:
        old = [row[0] for row in self._db.execute(
            "SELECT id FROM captures ORDER BY id DESC LIMIT -1 OFFSET ?", (keep,))]
        for entry_id in old:
            with self._db:
                self._db.execute("DELETE FROM captures WHERE id = ?", (entry_id,))
            self._image_path(entry_id).unlink(missing_ok=True)
            self._thumb_path(entry_id).unlink(missing_ok=True)

    # --- internos ----------------------------------------------------------

    def _emit_ocr(self, entry_id: int, future: Future[str]) -> None:
        try:
            text = future.result()
        except Exception:  # noqa: BLE001 - sem OCR a captura só não fica pesquisável
            log.debug("OCR do histórico falhou", exc_info=True)
            return
        if text.strip():
            self._ocrDone.emit(entry_id, text)

    def _image_path(self, entry_id: int) -> Path:
        return self.images / f"{entry_id}.png"

    def _thumb_path(self, entry_id: int) -> Path:
        return self.images / f"{entry_id}_thumb.jpg"

    def _entry(self, row: sqlite3.Row) -> Entry:
        return Entry(
            id=row["id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            source=row["source"],
            width=row["width"],
            height=row["height"],
            text=row["text"],
            image_path=self._image_path(row["id"]),
            thumb_path=self._thumb_path(row["id"]),
        )
