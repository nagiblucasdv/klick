"""Estrutura das tabelas, aprendida com o uso, para o autocompletar (SELECT, INSERT e UPDATE prontos).

Toda consulta que você copia ou salva na Análise ensina as tabelas e as colunas que ela cita: "c.nome"
com "FROM clientes c" diz que clientes tem nome. A grade convertida em INSERT ou UPDATE com o nome
da tabela ensina as colunas do cabeçalho. Fica num JSON ao lado do histórico.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from klick.analysis.fixes import SQL_KEYWORDS
from klick.analysis.query import Query, _mask, parse

log = logging.getLogger(__name__)

TEMPLATES = [("select", "SELECT"), ("insert", "INSERT"), ("update", "UPDATE")]
_IDENT = re.compile(r"[A-Za-z_][\w$]*")
_KEY = re.compile(r"^(id|cod|codigo|num|numero|seq)(_|$)|(_id|id)$|^cod[a-z]", re.IGNORECASE)  # coluna de chave


def _clean(name: str) -> str:
    return name.strip().strip('"[]`').lower()


def _column(expr: str) -> str | None:
    """Nome de coluna simples numa expressão ("c.nome" -> "nome", "nome" -> "nome"); None se for conta ou função."""
    expr = re.sub(r"\s+(as\s+)?[A-Za-z_]\w*$", "", expr.strip(), flags=re.IGNORECASE) if " " in expr.strip() else expr
    last = expr.strip().split(".")[-1].strip('"[]`')
    if not _IDENT.fullmatch(last) or last.upper() in SQL_KEYWORDS or last == "*":
        return None
    return last.lower()


class Schema:
    def __init__(self, path: Path):
        self.path = path
        self.tables: dict[str, list[str]] = {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.tables = {str(t): [str(c) for c in cols] for t, cols in data.get("tables", {}).items()}
        except (OSError, ValueError, AttributeError):
            pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"tables": self.tables}, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            log.warning("Não foi possível guardar a estrutura das tabelas", exc_info=True)

    def _add(self, table: str, column: str | None) -> bool:
        table = _clean(table)
        if not table or not _IDENT.fullmatch(table.split(".")[-1]) or table.upper() in SQL_KEYWORDS:
            return False
        cols = self.tables.setdefault(table, [])
        if column and column not in cols:
            cols.append(column)
            return True
        return False

    def learn_query(self, q: Query | str) -> int:
        """Aprende com uma consulta. Devolve quantas colunas novas."""
        q = parse(q) if isinstance(q, str) else q
        aliases = q.alias_map()
        if not aliases:
            return 0
        new = 0
        for table in aliases.values():
            self._add(table, None)
        masked = _mask(q.text)
        for m in re.finditer(r"\b([A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)\b", masked):
            table = aliases.get(m.group(1).lower())
            if table and not masked[m.end():m.end() + 1] == "(":
                new += self._add(table, _column(m.group(2)))
        only = next(iter(aliases.values())) if len(set(aliases.values())) == 1 else None
        if only:  # uma tabela só: as colunas sem apelido também são dela
            for expr in [*q.columns, *(c for c, _ in q.assignments), *q.group, *(e for e, _ in q.order)]:
                if "." not in expr and "(" not in expr:
                    new += self._add(only, _column(expr))
            for cond in q.filters:
                m = re.match(r"(?:AND\s+|OR\s+)?([A-Za-z_][\w$]*)\s*(=|<|>|!|<>|\bin\b|\blike\b|\bis\b|\bbetween\b)",
                             cond, re.IGNORECASE)
                if m:
                    new += self._add(only, _column(m.group(1)))
        self.save()
        return new

    def learn_columns(self, table: str, columns: list[str]) -> int:
        new = sum(self._add(table, _column(c)) for c in columns)
        self.save()
        return new

    def forget(self, table: str) -> None:
        self.tables.pop(table, None)
        self.save()

    def search(self, text: str) -> list[str]:
        """Tabelas que contêm o que foi digitado; as que começam com ele vêm primeiro."""
        text = text.strip().lower()
        names = sorted(self.tables)
        if not text:
            return names
        starts = [t for t in names if t.split(".")[-1].startswith(text)]
        return starts + [t for t in names if text in t and t not in starts]

    def template(self, table: str, kind: str) -> str:
        cols = self.tables.get(table, [])
        name = table
        short = table.split(".")[-1]
        alias = "".join(part[0] for part in short.split("_") if part)[:3] or short[0]
        if kind == "select":
            if not cols:
                return f"SELECT *\nFROM {name} {alias}\nWHERE "
            first, *rest = cols
            lines = [f"SELECT {alias}.{first}"] + [f"       {alias}.{c}" for c in rest]
            return ",\n".join(lines) + f"\nFROM {name} {alias}\nWHERE "
        if kind == "insert":
            if not cols:
                return f"INSERT INTO {name} ()\nVALUES ();"
            return (f"INSERT INTO {name} ({', '.join(cols)})\n"
                    f"VALUES ({', '.join(f'/* {c} */' for c in cols)});")
        if not cols:
            return f"UPDATE {name}\n   SET \n WHERE ;"
        key = next((c for c in cols if _KEY.search(c)), cols[0])
        sets = [c for c in cols if c != key] or [key]
        body = ",\n       ".join(f"{c} = /* {c} */" for c in sets)
        return f"UPDATE {name}\n   SET {body}\n WHERE {key} = /* {key} */;"
