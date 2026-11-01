"""Grade de resultado lida de um print (SSMS, DBeaver, planilha): as colunas, o cabeçalho, as células que
o OCR pode ter errado, o resumo de cada coluna e a conversão para Excel, CSV, Markdown, INSERT, UPDATE e JSON.

As colunas saem do alinhamento de todas as linhas juntas: cada linha é cortada onde há um espaço bem
maior que o normal entre palavras, e os pedaços que se sobrepõem na horizontal (de qualquer linha) são
a mesma coluna. Assim uma célula vazia não empurra o resto da linha para a coluna errada.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from statistics import median

from klick.analysis.layout import visual_lines


def _cells(line, gap: float) -> list[tuple[float, float, str]]:
    cells = [[line[0]]]
    for w in line[1:]:
        if w.rect.left() - cells[-1][-1].rect.right() > gap:
            cells.append([w])
        else:
            cells[-1].append(w)
    return [(c[0].rect.left(), c[-1].rect.right(), " ".join(w.text for w in c)) for c in cells]


def table_rows(words) -> list[list[str]]:
    lines = visual_lines(words)
    if not lines:
        return []
    height = median(w.rect.height() for line in lines for w in line)
    gap = max(height * 0.9, 8.0)
    rows = [_cells(line, gap) for line in lines]
    # As colunas vêm das linhas de dados: um título largo em cima de duas colunas não deve juntá-las.
    sample = rows[1:] if len(rows) >= 3 else rows
    spans = sorted((left, right) for row in sample for left, right, _ in row)
    columns: list[list[float]] = []
    for left, right in spans:
        if columns and left <= columns[-1][1] + gap * 0.3:
            columns[-1][1] = max(columns[-1][1], right)
        else:
            columns.append([left, right])
    out = []
    for row in rows:
        values = [""] * len(columns)
        for left, right, text in row:
            def overlap(col: list[float]) -> float:
                return min(right, col[1]) - max(left, col[0])
            best = max(range(len(columns)), key=lambda i: (overlap(columns[i]),
                                                           -abs((left + right) / 2 - sum(columns[i]) / 2)))
            values[best] = f"{values[best]} {text}".strip()
        out.append(values)
    return out


def looks_like_table(rows: list[list[str]]) -> bool:
    """Pelo menos duas colunas, e duas linhas com dado em mais de uma coluna."""
    if not rows or len(rows[0]) < 2:
        return False
    return sum(1 for r in rows if sum(1 for v in r if v) >= 2) >= 2


# --- números e tipos --------------------------------------------------------------------

def number(value: str, comma_decimal: bool = True) -> float | None:
    """Número de uma célula: 1240.50, 1.240,50 (vírgula decimal), R$ 7, 12%. None se não for."""
    v = re.sub(r"^(R\$|US\$|\$)\s*", "", value.strip()).rstrip("%").strip()
    if not v:
        return None
    if comma_decimal and re.fullmatch(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?", v):
        v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def has_header(rows: list[list[str]]) -> bool:
    """A primeira linha é título se não tem número e, embaixo dela, alguma coluna é de números."""
    if len(rows) < 2:
        return False
    first = [v for v in rows[0] if v.strip()]
    if not first or any(number(v) is not None for v in first):
        return False
    for c in range(len(rows[0])):
        below = [r[c] for r in rows[1:] if c < len(r) and r[c].strip()]
        if below and sum(number(v) is not None for v in below) >= max(1, len(below) * 0.6):
            return True
    return len(rows) >= 3 and len(set(rows[0])) == len(rows[0])  # só texto: títulos diferentes entre si


_DIGIT_LOOKALIKE = str.maketrans({"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8",
                                  "Z": "2"})


def suspicious(rows: list[list[str]], header: bool) -> dict[tuple[int, int], str]:
    """Célula de coluna de números que o OCR leu com letra: {(linha, coluna): "valor sugerido"}."""
    out = {}
    data = list(enumerate(rows))[1 if header else 0:]
    for c in range(len(rows[0]) if rows else 0):
        filled = [(r, row[c]) for r, row in data if c < len(row) and row[c].strip()]
        numeric = [v for _, v in filled if number(v) is not None]
        if len(filled) < 3 or len(numeric) < len(filled) * 0.6:
            continue
        for r, value in filled:
            if number(value) is None:
                guess = value.translate(_DIGIT_LOOKALIKE)
                if number(guess) is not None:
                    out[(r, c)] = guess
    return out


@dataclass
class ColumnStats:
    name: str
    kind: str  # "número", "data", "texto" ou "vazia"
    filled: int
    total: int
    distinct: int
    sum: float | None = None
    mean: float | None = None
    min: float | None = None
    max: float | None = None
    integers: bool = False  # todos os números são inteiros (cara de código)


_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}")


def column_name(name: str, index: int) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    plain = re.sub(r"\W+", "_", plain).strip("_").lower()
    return plain if plain and not plain[0].isdigit() else f"coluna{index + 1}"


def columns(rows: list[list[str]], header: bool = True) -> list[str]:
    if not rows:
        return []
    if header:
        return [column_name(c, i) for i, c in enumerate(rows[0])]
    return [f"coluna{i + 1}" for i in range(len(rows[0]))]


def data_rows(rows: list[list[str]], header: bool) -> list[list[str]]:
    return [r for r in (rows[1:] if header else rows) if any(v.strip() for v in r)]


def column_stats(rows: list[list[str]], header: bool = True, comma_decimal: bool = True) -> list[ColumnStats]:
    names = columns(rows, header)
    data = data_rows(rows, header)
    out = []
    for i, name in enumerate(names):
        values = [r[i].strip() for r in data if i < len(r)]
        filled = [v for v in values if v]
        numbers = [n for n in (number(v, comma_decimal) for v in filled) if n is not None]
        if not filled:
            kind = "vazia"
        elif len(numbers) == len(filled):
            kind = "número"
        elif all(_DATE.fullmatch(v) for v in filled):
            kind = "data"
        else:
            kind = "texto"
        stats = ColumnStats(name, kind, len(filled), len(values), len(set(filled)))
        if kind == "número":
            stats.sum = sum(numbers)
            stats.mean = stats.sum / len(numbers)
            stats.min, stats.max = min(numbers), max(numbers)
            stats.integers = all(n == int(n) for n in numbers)
        out.append(stats)
    return out


def repeated(rows: list[list[str]], header: bool, column: int = 0) -> list[str]:
    """Valores que aparecem mais de uma vez na coluna (em geral a chave: código, id)."""
    seen: dict[str, int] = {}
    for r in data_rows(rows, header):
        if column < len(r) and r[column].strip():
            seen[r[column].strip()] = seen.get(r[column].strip(), 0) + 1
    return [v for v, n in seen.items() if n > 1]


_KEY_NAME = re.compile(r"^(id|cod|codigo|num|numero|nr|seq)(_|$)|(_id|_cod|id)$|^cod[a-z]", re.IGNORECASE)


def key_like(stats: ColumnStats, first: bool = False) -> bool:
    """Coluna de código ou id: nome de chave, ou a primeira coluna só com inteiros diferentes. Somar não diz nada."""
    return bool(_KEY_NAME.search(stats.name)) or (first and stats.integers and stats.distinct == stats.filled > 1)


def brl(value: float) -> str:
    """1240.5 -> "1.240,50"; inteiros ficam sem casas."""
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def describe(rows: list[list[str]], header: bool, stats: list[ColumnStats]) -> str:
    data = data_rows(rows, header)
    head = f"{len(data)} linha{'s' if len(data) != 1 else ''} e {len(stats)} coluna{'s' if len(stats) != 1 else ''}"
    sums = [f"{s.name} soma {brl(s.sum)}" for i, s in enumerate(stats)
            if s.sum is not None and not key_like(s, first=i == 0)][:2]
    dup = repeated(rows, header)
    extra = []
    if sums:
        extra.append(", ".join(sums))
    if dup:
        extra.append(f"{len(dup)} valor{'es' if len(dup) != 1 else ''} repetido{'s' if len(dup) != 1 else ''} em "
                     f"{stats[0].name}" if stats else "")
    return head + (": " + "; ".join(e for e in extra if e) if extra else "") + "."


# --- saídas -----------------------------------------------------------------------------

def to_tsv(rows: list[list[str]]) -> str:
    """Separado por tabulação: cola direto em colunas no Excel ou no Google Planilhas."""
    return "\n".join("\t".join(r) for r in rows)


def to_csv(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";", lineterminator="\n").writerows(rows)  # ";" abre certo no Excel em pt-BR
    return buffer.getvalue().rstrip("\n")


def to_markdown(rows: list[list[str]], header: bool = True) -> str:
    """Tabela em Markdown, para colar em chat, chamado ou documentação."""
    if not rows:
        return ""
    names = rows[0] if header else columns(rows, False)
    body = rows[1:] if header else rows

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"

    return "\n".join([line(names), "| " + " | ".join("---" for _ in names) + " |", *(line(r) for r in body)])


def literal(value: str, comma_decimal: bool = False) -> str:
    """Valor SQL: número sem aspas, vazio vira NULL, texto entre aspas (apóstrofo dobrado)."""
    value = value.strip()
    if not value or value.upper() == "NULL":
        return "NULL"
    if re.fullmatch(r"-?\d+(\.\d+)?", value) and not (comma_decimal and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", value)):
        return value
    if comma_decimal and re.fullmatch(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?", value):
        return value.replace(".", "").replace(",", ".")
    return "'" + value.replace("'", "''") + "'"


def to_insert(rows: list[list[str]], table: str = "tabela", header: bool = True, comma_decimal: bool = False) -> str:
    names = ", ".join(columns(rows, header))
    table = table.strip() or "tabela"
    return "\n".join(f"INSERT INTO {table} ({names}) VALUES ({', '.join(literal(v, comma_decimal) for v in r)});"
                     for r in data_rows(rows, header))


def to_update(rows: list[list[str]], table: str = "tabela", key: int = 0, header: bool = True,
              comma_decimal: bool = False) -> str:
    """Um UPDATE por linha: as outras colunas no SET e a coluna `key` no WHERE."""
    names = columns(rows, header)
    if not names or key >= len(names):
        return ""
    table = table.strip() or "tabela"
    out = []
    for r in data_rows(rows, header):
        r = [*r, *[""] * (len(names) - len(r))]
        sets = ", ".join(f"{n} = {literal(v, comma_decimal)}" for i, (n, v) in enumerate(zip(names, r)) if i != key)
        out.append(f"UPDATE {table} SET {sets} WHERE {names[key]} = {literal(r[key], comma_decimal)};")
    return "\n".join(out)


def to_json(rows: list[list[str]], header: bool = True, comma_decimal: bool = True) -> str:
    """Um objeto por linha; números viram números."""
    names = columns(rows, header)
    items = []
    for r in data_rows(rows, header):
        item = {}
        for name, value in zip(names, r):
            n = number(value, comma_decimal) if value.strip() else None
            item[name] = None if not value.strip() else (int(n) if n is not None and n == int(n) and "," not in value
                                                         and "." not in value else n if n is not None else value)
        items.append(item)
    return json.dumps(items, indent=2, ensure_ascii=False)
