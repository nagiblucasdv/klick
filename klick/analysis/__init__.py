"""Análise: entende um print de código ou de dado (consulta SQL, JSON ou grade de resultado) e entrega
pronto para usar, dizendo o que é e o que pode estar errado.

- fixes: conserta o que o OCR estraga, guardando cada conserto para mostrar e desfazer
- layout: remonta o texto pela posição das palavras, com a indentação do print
- query, document, grid: SQL, JSON e tabelas
- schema: tabelas e colunas aprendidas, para o autocompletar de estrutura
"""

from __future__ import annotations

import re
from enum import Enum

from klick.analysis import document, grid, query
from klick.analysis.layout import layout_text


class Kind(str, Enum):
    SQL = "sql"
    JSON = "json"
    TABLE = "table"
    TEXT = "text"


def detect(result) -> Kind | None:
    """O tipo do que foi lido; None se não há texto. Texto comum vira Kind.TEXT."""
    if result is None or not result.words:
        return None
    text = layout_text(result)
    if document.looks_like_json(text):
        return Kind.JSON
    if query.looks_like_sql(text):
        return Kind.SQL
    if grid.looks_like_table(grid.table_rows(result.words)):
        return Kind.TABLE
    return Kind.TEXT


_ALNUM = re.compile(r"[0-9A-Za-zÀ-ÿ]{2,}")
_SYMBOLS = {"=", "*", ",", "(", ")", ">", "<", ">=", "<=", "<>", "!=", "-", "+", "/", ";", ".", "{", "}", "[", "]",
            ":", '":', "},", "],"}


def reading_score(text: str) -> int:
    """Quão limpa parece uma leitura de código: letras e números em palavras de verdade, menos uma multa por
    pedaço que é só sujeira (".o--.", "o", "d d"). Escolhe entre o OCR do Windows e o RapidOCR."""
    score = 0
    for token in text.split():
        if _ALNUM.search(token):
            score += sum(ch.isalnum() for ch in token)
        elif token not in _SYMBOLS:
            score -= 4
    return score
