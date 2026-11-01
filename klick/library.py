"""Biblioteca de consultas: as consultas SQL que você guarda com um nome, numa página só da galeria.

Fica num SQLite próprio (consultas.db, ao lado do histórico), separado da galeria: desligar o histórico
ou limpar capturas antigas não mexe nas consultas guardadas.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from klick.analysis import query

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    used_at TEXT,
    uses INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class SavedQuery:
    id: int
    name: str
    text: str
    created_at: datetime
    updated_at: datetime
    used_at: datetime | None
    uses: int

    @property
    def tables(self) -> list[str]:
        """Tabelas citadas (FROM, JOIN, UPDATE, INTO), sem repetir."""
        q = query.parse(self.text)
        out: list[str] = []
        for table, _ in [*q.tables, *((j.table, j.alias) for j in q.joins)]:
            if table.lower() not in out:
                out.append(table.lower())
        return out


def suggest_name(text: str) -> str:
    """Nome inicial para guardar: o tipo e as tabelas ("SELECT clientes + pedidos")."""
    q = query.parse(text)
    tables = [t for t, _ in [*q.tables, *((j.table, j.alias) for j in q.joins)]]
    if not tables:
        return "Consulta"
    return f"{q.kind or 'SQL'} {' + '.join(dict.fromkeys(t.lower() for t in tables))}"[:80]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Library(QObject):
    changed = Signal()

    def __init__(self, path: Path):
        super().__init__()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def add(self, name: str, text: str) -> int:
        now = _now()
        with self._db:
            cur = self._db.execute("INSERT INTO queries (name, text, created_at, updated_at) VALUES (?, ?, ?, ?)",
                                   (name.strip() or suggest_name(text), text, now, now))
        self.changed.emit()
        return cur.lastrowid

    def find_text(self, text: str) -> SavedQuery | None:
        """A consulta guardada com este mesmo texto (ignorando espaços e maiúsculas), se houver."""
        key = " ".join(text.split()).lower()
        for item in self.search():
            if " ".join(item.text.split()).lower() == key:
                return item
        return None

    def update(self, query_id: int, name: str | None = None, text: str | None = None) -> None:
        sets, args = ["updated_at = ?"], [_now()]
        if name is not None:
            sets.append("name = ?")
            args.append(name.strip() or "Consulta")
        if text is not None:
            sets.append("text = ?")
            args.append(text)
        with self._db:
            self._db.execute(f"UPDATE queries SET {', '.join(sets)} WHERE id = ?", (*args, query_id))
        self.changed.emit()

    def used(self, query_id: int) -> None:
        """Copiou: conta mais um uso (as mais usadas aparecem primeiro)."""
        with self._db:
            self._db.execute("UPDATE queries SET uses = uses + 1, used_at = ? WHERE id = ?", (_now(), query_id))
        self.changed.emit()

    def delete(self, query_id: int) -> None:
        with self._db:
            self._db.execute("DELETE FROM queries WHERE id = ?", (query_id,))
        self.changed.emit()

    def get(self, query_id: int) -> SavedQuery | None:
        row = self._db.execute("SELECT * FROM queries WHERE id = ?", (query_id,)).fetchone()
        return self._item(row) if row else None

    def search(self, text: str = "") -> list[SavedQuery]:
        """Todas as palavras digitadas no nome ou no texto; as mais usadas e as mais recentes primeiro."""
        sql, args = "SELECT * FROM queries", []
        terms = text.split()
        if terms:
            sql += " WHERE " + " AND ".join("(name LIKE ? OR text LIKE ?)" for _ in terms)
            for term in terms:
                args += [f"%{term}%", f"%{term}%"]
        sql += " ORDER BY uses DESC, COALESCE(used_at, updated_at) DESC, id DESC"
        return [self._item(row) for row in self._db.execute(sql, args)]

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM queries").fetchone()[0]

    def import_files(self, paths: list[Path]) -> int:
        """Cada .sql vira uma consulta com o nome do arquivo. Devolve quantas entraram (repetidas ficam de fora)."""
        added = 0
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8-sig").strip()
            except (OSError, UnicodeDecodeError):
                text = path.read_text(encoding="latin-1").strip() if path.exists() else ""
            if text and self.find_text(text) is None:
                self.add(path.stem.replace("_", " "), text)
                added += 1
        return added

    def export(self) -> str:
        """Todas num texto só, cada uma com o nome em comentário: um backup que abre em qualquer editor de SQL."""
        out = []
        for item in sorted(self.search(), key=lambda q: q.name.lower()):
            body = item.text.strip()
            out.append(f"-- {item.name}\n{body}{'' if body.endswith(';') else ';'}")
        return "\n\n".join(out) + ("\n" if out else "")

    @staticmethod
    def _item(row: sqlite3.Row) -> SavedQuery:
        return SavedQuery(row["id"], row["name"], row["text"], datetime.fromisoformat(row["created_at"]),
                          datetime.fromisoformat(row["updated_at"]),
                          datetime.fromisoformat(row["used_at"]) if row["used_at"] else None, row["uses"])
