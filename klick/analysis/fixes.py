"""Consertos do que o OCR estraga em código, cada um guardado para ser mostrado e desfeito.

O texto é percorrido uma vez só, da esquerda para a direita, sabendo o que é texto entre aspas e o que
é comentário: nada dentro deles é mexido (fora as próprias aspas curvas, que viram retas). Cada
conserto possível recebe um número na ordem em que aparece; desfazer é rodar de novo pulando aquele
número, o que dá o mesmo texto sem ele.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product

SQL_KEYWORDS = frozenset((
    "SELECT FROM WHERE AND OR NOT IN IS NULL JOIN LEFT RIGHT INNER OUTER FULL CROSS ON AS GROUP BY ORDER "
    "HAVING LIMIT OFFSET UNION ALL DISTINCT INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE VIEW INDEX "
    "DROP ALTER ADD COLUMN PRIMARY KEY FOREIGN REFERENCES CASE WHEN THEN ELSE END EXISTS BETWEEN LIKE ILIKE "
    "ASC DESC WITH COUNT SUM AVG MIN MAX COALESCE IFNULL CAST TOP FETCH FIRST ROWS ONLY RETURNING USING "
    "TRUE FALSE DEFAULT"
).split())

# O que o OCR confunde em fonte de código: o zero com O e D, o um com I e L, e assim por diante.
_LOOKALIKE = {"0": "OD", "1": "IL", "3": "E", "4": "A", "5": "S", "7": "T", "8": "B"}
_WORD = re.compile(r"[A-Za-z0-9_]+")
_OPEN_QUOTES = "'‘’´"
_OPEN_DQUOTES = '"“”'


@dataclass(frozen=True)
class Fix:
    start: int  # onde ficou no texto consertado
    end: int
    before: str
    after: str
    number: int  # ordem em que apareceu; é o que se passa em `skip` para desfazer


class _Out:
    """Texto sendo montado, com a lista de consertos e os que devem ser pulados."""

    def __init__(self, skip: frozenset[int]):
        self.parts: list[str] = []
        self.size = 0
        self.fixes: list[Fix] = []
        self.skip = skip
        self._count = 0

    def add(self, text: str) -> None:
        self.parts.append(text)
        self.size += len(text)

    def offer(self, before: str, after: str) -> None:
        """Um conserto possível: entra `after`, a menos que o usuário tenha desfeito este."""
        number = self._count
        self._count += 1
        if before == after or number in self.skip:
            self.add(before)
            return
        self.fixes.append(Fix(self.size, self.size + len(after), before, after, number))
        self.add(after)

    def text(self) -> str:
        return "".join(self.parts)


def keyword_lookalike(word: str) -> str | None:
    """"FR0M" -> "FROM", "SELEC7" -> "SELECT": a palavra-chave que o OCR leu com um número no lugar de letra."""
    if not any(ch.isdigit() for ch in word) or not any(ch.isalpha() for ch in word) or len(word) < 2:
        return None
    options = [_LOOKALIKE.get(ch, ch.upper()) for ch in word]
    if any(not opt for opt in options):
        return None
    for combo in product(*options):
        candidate = "".join(combo)
        if candidate in SQL_KEYWORDS:
            letters = [ch for ch in word if ch.isalpha()]
            return candidate if all(ch.isupper() for ch in letters) else candidate.lower()
    return None


def _quoted(text: str, i: int, closers: str, escape_double: bool) -> int:
    """Fim (exclusivo) do texto entre aspas que começa em i; len(text) se nunca fecha."""
    j = i + 1
    while j < len(text):
        if text[j] in closers:
            if escape_double and j + 1 < len(text) and text[j + 1] in closers:
                j += 2  # '' dentro do texto é um apóstrofo
                continue
            return j + 1
        j += 1
    return len(text)


@dataclass
class SqlFixes:
    text: str
    fixes: list[Fix]
    unclosed: str = ""  # "'" ou '"' se um texto entre aspas nunca fecha


def fix_sql(text: str, skip: frozenset[int] = frozenset()) -> SqlFixes:
    """Conserta aspas curvas, palavras-chave com número no lugar de letra (FR0M) e "c. codcli" -> "c.codcli"."""
    out = _Out(skip)
    unclosed = ""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.add(text[i:j])
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.add(text[i:j])
            i = j
        elif ch in _OPEN_QUOTES or ch in _OPEN_DQUOTES:
            single = ch in _OPEN_QUOTES
            j = _quoted(text, i, _OPEN_QUOTES if single else _OPEN_DQUOTES, escape_double=single)
            literal = text[i:j]
            straight = "'" if single else '"'
            closed = j <= n and len(literal) > 1 and literal[-1] in (_OPEN_QUOTES if single else _OPEN_DQUOTES)
            if not closed:
                unclosed = straight
            fixed = straight + literal[1:-1] + straight if closed else straight + literal[1:]
            out.offer(literal, fixed)
            i = j
        elif ch == "`":  # identificador do MySQL: fica como está
            j = text.find("`", i + 1)
            j = n if j < 0 else j + 1
            out.add(text[i:j])
            i = j
        elif (m := _WORD.match(text, i)) is not None:
            word = m.group()
            j = m.end()
            fixed = keyword_lookalike(word) or word
            # "c. codcli": o OCR do Windows separa o apelido da coluna; fora de texto, isso nunca é SQL válido.
            # Vira um conserto só, com as duas pontas, para a lista mostrar "c. codcli -> c.codcli".
            after = _WORD.match(text, j + 2) if text.startswith(". ", j) and not word.isdigit() else None
            if after is not None and not after.group()[0].isdigit():
                out.offer(f"{word}. {after.group()}", f"{fixed}.{after.group()}")
                i = after.end()
            else:
                out.offer(word, fixed)
                i = j
        else:
            out.add(ch)
            i += 1
    return SqlFixes(out.text(), out.fixes, unclosed)


_PY_LITERALS = {"True": "true", "False": "false", "None": "null"}
_KEY = re.compile(r"[A-Za-z_][\w-]*")


def fix_json(text: str, skip: frozenset[int] = frozenset()) -> tuple[str, list[Fix]]:
    """Conserta o que o OCR e os logs estragam num JSON, sem mexer dentro dos textos: aspas curvas e
    simples, True/False/None do Python, chave sem aspas e vírgula sobrando antes de } ou ]."""
    out = _Out(skip)
    i, n = 0, len(text)
    last = ""  # último caractere que não é espaço, fora dos textos
    while i < n:
        ch = text[i]
        if ch in _OPEN_DQUOTES:
            j = _quoted(text, i, _OPEN_DQUOTES, escape_double=False)
            j = _skip_escaped(text, i, j, _OPEN_DQUOTES)
            literal = text[i:j]
            closed = len(literal) > 1 and literal[-1] in _OPEN_DQUOTES
            out.offer(literal, '"' + literal[1:-1] + '"' if closed else '"' + literal[1:])
            last = '"'
            i = j
        elif ch in _OPEN_QUOTES:
            j = _quoted(text, i, _OPEN_QUOTES, escape_double=False)
            j = _skip_escaped(text, i, j, _OPEN_QUOTES)
            literal = text[i:j]
            inner = literal[1:-1] if len(literal) > 1 and literal[-1] in _OPEN_QUOTES else literal[1:]
            inner = inner.replace("\\'", "'").replace('\\"', '"').replace('"', '\\"')
            out.offer(literal, f'"{inner}"')
            last = '"'
            i = j
        elif ch == "," and _next_closer(text, i + 1):
            out.offer(",", "")  # vírgula antes de } ou ]: o JSON não aceita
            i += 1
        elif (m := _KEY.match(text, i)) is not None and not (i and (text[i - 1].isalnum() or text[i - 1] in "_.-")):
            word = m.group()
            j = m.end()
            rest = text[j:j + 40].lstrip()
            if last and last in "{," and rest.startswith(":"):
                out.offer(word, f'"{word}"')
            elif word in _PY_LITERALS:
                out.offer(word, _PY_LITERALS[word])
            else:
                out.add(word)
            last = word[-1]
            i = j
        else:
            out.add(ch)
            if not ch.isspace():
                last = ch
            i += 1
    return out.text(), out.fixes


def _skip_escaped(text: str, i: int, j: int, closers: str) -> int:
    """Ajusta o fim do texto entre aspas: aspa precedida de barra (\\") não fecha."""
    while j <= len(text) and j - 1 > i and text[j - 2] == "\\" and text[j - 1] in closers:
        j = _quoted(text, j - 1, closers, escape_double=False)
    return j


def _next_closer(text: str, i: int) -> bool:
    while i < len(text) and text[i].isspace():
        i += 1
    return i < len(text) and text[i] in "}]"
