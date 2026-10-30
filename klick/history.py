"""Histórico pesquisável: cada captura vira uma linha no SQLite com o texto do OCR.

A busca usa FTS5 com remove_diacritics, então "erro" acha "Erro" e "atencao"
acha "Atenção". O OCR das capturas roda em segundo plano depois de salvar.

As capturas se dividem em cinco coleções: prints (copiados, salvos ou editados),
gravações (MP4), GIFs, leituras (o que passou pelo OCR) e análises (SQL, JSON, tabelas).

Cada item é temporário (só na galeria, some depois de alguns dias) ou guardado (o
arquivo está na pasta do tipo). Guardar copia o print ou o texto para a pasta, ou move
a gravação que estava na pasta interna da galeria.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
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
# Colunas que chegaram depois; bancos antigos ganham na abertura.
MIGRATIONS = {
    "kind": "ALTER TABLE captures ADD COLUMN kind TEXT NOT NULL DEFAULT 'image'",
    "media": "ALTER TABLE captures ADD COLUMN media TEXT",
    "duration": "ALTER TABLE captures ADD COLUMN duration REAL",
    "temp": "ALTER TABLE captures ADD COLUMN temp INTEGER NOT NULL DEFAULT 0",
    "saved": "ALTER TABLE captures ADD COLUMN saved TEXT",
}


class Collection(str, Enum):
    PRINTS = "prints"
    RECORDINGS = "recordings"
    GIFS = "gifs"
    READING = "reading"
    ANALYSIS = "analysis"


# Como cada coleção aparece no SQL.
FILTERS = {
    Collection.PRINTS: "c.kind = 'image' AND c.source NOT IN ('ocr', 'sql')",
    Collection.RECORDINGS: "c.kind = 'video'",
    Collection.GIFS: "c.kind = 'gif'",
    Collection.READING: "c.kind = 'image' AND c.source = 'ocr'",
    Collection.ANALYSIS: "c.kind = 'image' AND c.source = 'sql'",
}
# Pasta de cada coleção (config.FOLDERS); análises vão junto com as leituras.
FOLDER_KIND = {Collection.PRINTS: "prints", Collection.RECORDINGS: "recordings", Collection.GIFS: "gifs",
               Collection.READING: "reading", Collection.ANALYSIS: "reading"}


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
    kind: str = "image"
    media: Path | None = None  # arquivo da gravação ou do GIF
    duration: float | None = None
    temp: bool = False  # só na galeria: some depois de config.temp_days()
    saved: Path | None = None  # cópia guardada na pasta (prints e leituras)

    @property
    def collection(self) -> Collection:
        if self.kind == "video":
            return Collection.RECORDINGS
        if self.kind == "gif":
            return Collection.GIFS
        return {"ocr": Collection.READING, "sql": Collection.ANALYSIS}.get(self.source, Collection.PRINTS)

    def expires_in(self, days: int, now: datetime | None = None) -> int | None:
        """Dias até sumir (0 = hoje), ou None se está guardado ou nada expira."""
        if not self.temp or days <= 0:
            return None
        left = self.created_at + timedelta(days=days) - (now or datetime.now())
        return max(0, left.days + (1 if left.seconds else 0))


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
        self.media_dir = self.root / "media"  # gravações e GIFs que ficam só na galeria
        self._run_ocr = run_ocr
        self._db = sqlite3.connect(self.root / "history.db")
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        columns = {row["name"] for row in self._db.execute("PRAGMA table_info(captures)")}
        with self._db:
            for name, sql in MIGRATIONS.items():
                if name not in columns:
                    self._db.execute(sql)
        self._ocrDone.connect(self.set_text)

    def close(self) -> None:
        self._db.close()

    @property
    def enabled(self) -> bool:
        return config.history_enabled()

    def add(self, image: QImage, source: str, text: str | None = None, temp: bool = False,
            saved: Path | None = None) -> int | None:
        """Guarda a captura. Sem `text`, roda o OCR em segundo plano para indexar."""
        if not self.enabled or image.isNull():
            return None
        entry_id = self._insert(source, image, text or "", "image", temp=temp, saved=saved)
        image.save(str(self._image_path(entry_id)), "PNG")
        if text is None and self._run_ocr:
            ocr.recognize(image, config.ocr_language()).add_done_callback(
                lambda future: self._emit_ocr(entry_id, future))
        self.prune(config.history_max_items())
        self.changed.emit()
        return entry_id

    def add_media(self, path: Path, kind: str, frame: QImage, duration: float | None = None,
                  temp: bool = False) -> int | None:
        """Guarda uma gravação ("video") ou GIF ("gif"). `frame` vira a miniatura; o arquivo fica onde está
        (na pasta do tipo, ou em media/ quando é temporário)."""
        if not self.enabled:
            return None
        entry_id = self._insert("record" if kind == "video" else "gif", frame, path.stem, kind,
                                media=str(path), duration=duration, temp=temp)
        self.prune(config.history_max_items())
        self.changed.emit()
        return entry_id

    def set_text(self, entry_id: int, text: str) -> None:
        with self._db:
            self._db.execute("UPDATE captures SET text = ? WHERE id = ?", (text, entry_id))
        self.changed.emit()

    def search(self, query: str = "", limit: int = 200, collection: Collection | None = None,
               temp_only: bool = False) -> list[Entry]:
        match = fts_query(query)
        where = [FILTERS[collection]] if collection else []
        if temp_only:
            where.append("c.temp = 1")
        args: list = []
        if match:
            sql = "SELECT c.* FROM captures c JOIN captures_fts f ON f.rowid = c.id WHERE captures_fts MATCH ?"
            args.append(match)
            sql += "".join(f" AND {w}" for w in where)
        else:
            sql = "SELECT c.* FROM captures c" + (f" WHERE {' AND '.join(where)}" if where else "")
        rows = self._db.execute(sql + " ORDER BY c.id DESC LIMIT ?", (*args, limit))
        return [self._entry(row) for row in rows]

    def counts(self, query: str = "") -> dict[Collection, int]:
        """Quantas capturas cada coleção tem (já filtradas pela busca)."""
        match = fts_query(query)
        out = {}
        for collection, condition in FILTERS.items():
            if match:
                sql = ("SELECT COUNT(*) FROM captures c JOIN captures_fts f ON f.rowid = c.id "
                       f"WHERE captures_fts MATCH ? AND {condition}")
                out[collection] = self._db.execute(sql, (match,)).fetchone()[0]
            else:
                out[collection] = self._db.execute(f"SELECT COUNT(*) FROM captures c WHERE {condition}").fetchone()[0]
        return out

    def get(self, entry_id: int) -> Entry | None:
        row = self._db.execute("SELECT * FROM captures WHERE id = ?", (entry_id,)).fetchone()
        return self._entry(row) if row else None

    def delete(self, entry_id: int, remove_file: bool = False) -> None:
        """Tira a captura da galeria. Com `remove_file`, apaga também o arquivo da gravação ou do GIF;
        sem, ele continua na pasta onde foi salvo."""
        if remove_file and (entry := self.get(entry_id)) is not None and entry.media:
            entry.media.unlink(missing_ok=True)
        with self._db:
            self._db.execute("DELETE FROM captures WHERE id = ?", (entry_id,))
        self._image_path(entry_id).unlink(missing_ok=True)
        self._thumb_path(entry_id).unlink(missing_ok=True)
        self.changed.emit()

    def keep(self, entry_id: int) -> Path | None:
        """Guarda na pasta o que estava só na galeria. Devolve onde ficou o arquivo."""
        entry = self.get(entry_id)
        if entry is None:
            return None
        if not entry.temp:
            return entry.media or entry.saved
        folder = config.folder(FOLDER_KIND[entry.collection])
        folder.mkdir(parents=True, exist_ok=True)
        name = config.default_filename(entry.created_at)
        media, saved = entry.media, entry.saved
        if entry.media:
            target = folder / entry.media.name
            shutil.move(str(entry.media), target)
            media = target
        elif entry.collection in (Collection.READING, Collection.ANALYSIS) and entry.text.strip():
            saved = folder / Path(name).with_suffix(".txt").name
            saved.write_text(entry.text, encoding="utf-8")
        else:
            saved = folder / name
            shutil.copyfile(entry.image_path, saved)
        with self._db:
            self._db.execute("UPDATE captures SET temp = 0, media = ?, saved = ? WHERE id = ?",
                             (str(media) if media else None, str(saved) if saved else None, entry_id))
        self.changed.emit()
        return media or saved

    def expire(self, days: int, now: datetime | None = None) -> int:
        """Apaga o que está só na galeria há mais de `days` dias (0 = nunca). Devolve quantos."""
        if days <= 0:
            return 0
        limit = ((now or datetime.now()) - timedelta(days=days)).isoformat(timespec="seconds")
        old = [row[0] for row in self._db.execute(
            "SELECT id FROM captures WHERE temp = 1 AND created_at < ?", (limit,))]
        for entry_id in old:
            self.delete(entry_id, remove_file=True)
        return len(old)

    def temp_count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM captures WHERE temp = 1").fetchone()[0]

    def prune(self, keep: int) -> None:
        old = [row[0] for row in self._db.execute(
            "SELECT id FROM captures ORDER BY id DESC LIMIT -1 OFFSET ?", (keep,))]
        for entry_id in old:
            with self._db:
                self._db.execute("DELETE FROM captures WHERE id = ?", (entry_id,))
            self._image_path(entry_id).unlink(missing_ok=True)
            self._thumb_path(entry_id).unlink(missing_ok=True)

    # --- internos ----------------------------------------------------------

    def _insert(self, source: str, image: QImage, text: str, kind: str, media: str | None = None,
                duration: float | None = None, temp: bool = False, saved: Path | None = None) -> int:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO captures (created_at, source, width, height, text, kind, media, duration, temp, saved) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), source, image.width(), image.height(), text, kind,
                 media, duration, int(temp), str(saved) if saved else None),
            )
        entry_id = cur.lastrowid
        if not image.isNull():
            thumb = image.scaledToWidth(min(THUMB_WIDTH, image.width()), Qt.TransformationMode.SmoothTransformation)
            thumb.save(str(self._thumb_path(entry_id)), "JPG", 85)
        return entry_id

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
            kind=row["kind"],
            media=Path(row["media"]) if row["media"] else None,
            duration=row["duration"],
            temp=bool(row["temp"]),
            saved=Path(row["saved"]) if row["saved"] else None,
        )
