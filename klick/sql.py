"""O que a Análise entende num print (extra ligado por padrão; desliga nas configurações).

- Consulta SQL: conserta erros típicos do OCR, formata (palavras-chave em maiúsculas, uma
  cláusula por linha) e resume tabelas, junções, filtros e ordenação.
- JSON (log, resposta de API): conserta aspas e vírgulas que o OCR estraga, valida,
  formata e conta chaves e itens.
- Grade de resultado (SSMS, DBeaver, planilha): vira texto para o Excel, CSV, INSERT ou
  UPDATE, com um resumo por coluna (tipo, preenchidos, soma, média, mínimo e máximo).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from klick import theme

KEYWORDS = (
    "SELECT FROM WHERE AND OR NOT IN IS NULL JOIN LEFT RIGHT INNER OUTER FULL CROSS ON AS GROUP BY ORDER "
    "HAVING LIMIT OFFSET UNION ALL DISTINCT INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE VIEW INDEX "
    "DROP ALTER ADD COLUMN PRIMARY KEY FOREIGN REFERENCES CASE WHEN THEN ELSE END EXISTS BETWEEN LIKE "
    "ASC DESC WITH COUNT SUM AVG MIN MAX COALESCE IFNULL CAST TOP"
).split()
# Pares que só aparecem juntos em SQL: dois deles e o texto é quase certamente uma consulta.
CLUES = [r"\bselect\b.+\bfrom\b", r"\bupdate\b.+\bset\b", r"\binsert\s+into\b", r"\bdelete\s+from\b",
         r"\bcreate\s+(table|view|index)\b", r"\bwhere\b", r"\bjoin\b.+\bon\b", r"\bgroup\s+by\b",
         r"\border\s+by\b", r"\bvalues\s*\("]

# Trocas que o OCR costuma fazer em código.
OCR_FIXES = [
    (r"[‘’´`]", "'"),
    (r"[“”]", '"'),
    (r"\bSELEC[T7]\b", "SELECT"),
    (r"\bFR0M\b", "FROM"),
    (r"\bWH[E3]R[E3]\b", "WHERE"),
    (r"\b0R\b", "OR"),
    (r"\bAN0\b", "AND"),
    (r"\bN[U0]LL\b", "NULL"),
    (r"\b0RDER\b", "ORDER"),
    (r"\bGR0UP\b", "GROUP"),
    (r"\bJ0IN\b", "JOIN"),
    (r"\s*;\s*$", ";"),
    (r"\b([A-Za-z_]\w*)\. (\w)", r"\1.\2"),  # "c. codcli" (OCR do Windows) -> "c.codcli"
]


def looks_like_sql(text: str) -> bool:
    flat = " ".join(text.split()).lower()
    return sum(bool(re.search(clue, flat)) for clue in CLUES) >= 2


def fix_ocr(text: str) -> str:
    for pattern, repl in OCR_FIXES:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE | re.MULTILINE)
    return text


def tidy(text: str) -> str:
    """Conserta e formata o SQL lido. Sem o sqlparse, só conserta."""
    text = fix_ocr(text)
    try:
        import sqlparse
    except ImportError:
        return text
    return sqlparse.format(" ".join(text.split()), reindent=True, keyword_case="upper", indent_width=4).strip()


def tables(text: str) -> list[str]:
    """Tabelas citadas depois de FROM, JOIN, INTO e UPDATE, na ordem em que aparecem."""
    found = re.findall(r"\b(?:from|join|into|update)\s+([\w.\"\[\]]+)", text, flags=re.IGNORECASE)
    out: list[str] = []
    for name in found:
        name = name.strip('"[]')
        if name.lower() not in out and name.upper() not in KEYWORDS and not name.startswith("("):
            out.append(name.lower())
    return out


class SqlHighlighter(QSyntaxHighlighter):
    """Cores do SQL no painel da leitura: palavras-chave, textos, números e comentários."""

    def __init__(self, document):
        super().__init__(document)

        def fmt(color: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.DemiBold)
            return f

        self._rules = [
            (QRegularExpression(r"\b(" + "|".join(KEYWORDS) + r")\b",
                                QRegularExpression.PatternOption.CaseInsensitiveOption), fmt(theme.S600, True)),
            (QRegularExpression(r"\b\d+(\.\d+)?\b"), fmt("#1c6fb8")),
            (QRegularExpression(r"'[^']*'"), fmt("#9a5b00")),
            (QRegularExpression(r"--[^\n]*"), fmt(theme.G500)),
        ]

    def highlightBlock(self, text: str) -> None:
        for pattern, form in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), form)


# --- tabelas: grade de resultado (SSMS, DBeaver, planilha) lida do print -------------

def table_rows(words) -> list[list[str]]:
    """Monta a grade a partir das palavras e da posição delas na imagem.

    Linhas: palavras com o centro na mesma faixa de altura. Células: dentro da linha, um
    espaço bem maior que o normal entre duas palavras separa colunas. As colunas seguem
    a linha com mais células (em geral o cabeçalho), pela posição de cada célula.
    """
    words = [w for w in words if w.text.strip()]
    if not words:
        return []
    heights = sorted(w.rect.height() for w in words)
    height = heights[len(heights) // 2]
    rows: list[list] = []
    for w in sorted(words, key=lambda w: w.rect.center().y()):
        row = rows[-1] if rows else None
        if row is not None and abs(w.rect.center().y() - sum(x.rect.center().y() for x in row) / len(row)) < height * 0.55:
            row.append(w)
        else:
            rows.append([w])
    gap = max(height * 0.9, 8.0)
    grid: list[list[tuple[float, float, str]]] = []  # (esquerda, direita, texto) de cada célula
    for row in rows:
        row.sort(key=lambda w: w.rect.left())
        cells = [[row[0]]]
        for w in row[1:]:
            if w.rect.left() - cells[-1][-1].rect.right() > gap:
                cells.append([w])
            else:
                cells[-1].append(w)
        grid.append([(c[0].rect.left(), c[-1].rect.right(), " ".join(w.text for w in c)) for c in cells])
    anchors = max(grid, key=len)
    out = []
    for cells in grid:
        values = [""] * len(anchors)
        for left, right, text in cells:
            center = (left + right) / 2
            col = min(range(len(anchors)), key=lambda i: abs((anchors[i][0] + anchors[i][1]) / 2 - center))
            values[col] = f"{values[col]} {text}".strip()
        out.append(values)
    return out


def looks_like_table(rows: list[list[str]]) -> bool:
    """Pelo menos duas colunas e duas linhas com dado em mais de uma coluna."""
    if not rows or len(rows[0]) < 2:
        return False
    return sum(1 for r in rows if sum(1 for v in r if v) >= 2) >= 2


def to_tsv(rows: list[list[str]]) -> str:
    """Separado por tabulação: cola direto em colunas no Excel ou no Google Planilhas."""
    return "\n".join("\t".join(r) for r in rows)


def to_csv(rows: list[list[str]]) -> str:
    import csv
    import io

    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";", lineterminator="\n").writerows(rows)  # ";" abre certo no Excel em pt-BR
    return buffer.getvalue().rstrip("\n")


def _column(name: str, index: int) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    plain = re.sub(r"\W+", "_", plain).strip("_").lower()
    return plain if plain and not plain[0].isdigit() else f"coluna{index + 1}"


def _literal(value: str, comma_decimal: bool = False) -> str:
    """Valor SQL: número sem aspas, vazio vira NULL, texto entre aspas (apóstrofo dobrado).

    Com `comma_decimal`, número no formato brasileiro (1.240,50) vira 1240.50.
    """
    value = value.strip()
    if not value or value.upper() == "NULL":
        return "NULL"
    if re.fullmatch(r"-?\d+(\.\d+)?", value) and not (comma_decimal and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", value)):
        return value
    if comma_decimal and re.fullmatch(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?", value):
        return value.replace(".", "").replace(",", ".")
    return "'" + value.replace("'", "''") + "'"


def columns(rows: list[list[str]], header: bool = True) -> list[str]:
    """Nomes das colunas: a primeira linha (limpa) ou coluna1, coluna2…"""
    if not rows:
        return []
    if header:
        return [_column(c, i) for i, c in enumerate(rows[0])]
    return [f"coluna{i + 1}" for i in range(len(rows[0]))]


def _data(rows: list[list[str]], header: bool) -> list[list[str]]:
    return [r for r in (rows[1:] if header else rows) if any(v.strip() for v in r)]


def to_insert(rows: list[list[str]], table: str = "tabela", header: bool = True, comma_decimal: bool = False) -> str:
    """Um INSERT por linha. Com `header`, a primeira linha vira o nome das colunas."""
    names = ", ".join(columns(rows, header))
    table = table.strip() or "tabela"
    return "\n".join(f"INSERT INTO {table} ({names}) VALUES ({', '.join(_literal(v, comma_decimal) for v in r)});"
                     for r in _data(rows, header))


def to_update(rows: list[list[str]], table: str = "tabela", key: int = 0, header: bool = True,
              comma_decimal: bool = False) -> str:
    """Um UPDATE por linha: as outras colunas no SET e a coluna `key` no WHERE."""
    names = columns(rows, header)
    if not names or key >= len(names):
        return ""
    table = table.strip() or "tabela"
    out = []
    for r in _data(rows, header):
        sets = ", ".join(f"{n} = {_literal(v, comma_decimal)}" for i, (n, v) in enumerate(zip(names, r)) if i != key)
        out.append(f"UPDATE {table} SET {sets} WHERE {names[key]} = {_literal(r[key], comma_decimal)};")
    return "\n".join(out)


def kind(text: str) -> str:
    """Tipo da consulta pela primeira palavra-chave: SELECT, UPDATE, INSERT, DELETE, CREATE…"""
    match = re.search(r"\b(select|update|insert|delete|create|alter|drop|with)\b", text, flags=re.IGNORECASE)
    return match.group(1).upper() if match else ""


_ALNUM = re.compile(r"[0-9A-Za-zÀ-ÿ]{2,}")
_SYMBOLS = {"=", "*", ",", "(", ")", ">", "<", ">=", "<=", "<>", "!=", "-", "+", "/", ";", "."}


def reading_score(text: str) -> int:
    """Quão limpa parece uma leitura de código: letras e números em palavras de verdade,
    menos uma multa por pedaço que é só sujeira (".o--.", "o", "d d"). Para escolher
    entre o OCR do Windows e o RapidOCR."""
    score = 0
    for token in text.split():
        if _ALNUM.search(token):
            score += sum(ch.isalnum() for ch in token)
        elif token not in _SYMBOLS:
            score -= 4
    return score


# --- resumo da consulta -------------------------------------------------------------

_STOP = r"(?:left|right|inner|full|cross|join|where|group\s+by|order\s+by|having|limit|union)"


def joins(text: str) -> list[str]:
    """Cada junção numa linha: "LEFT JOIN pedidos p ON p.codcli = c.codcli"."""
    flat = " ".join(text.split())
    found = re.findall(r"\b((?:(?:left|right|inner|full|cross)\s+)?(?:outer\s+)?join\s+.+?)"
                       rf"(?=\s+{_STOP}\b|;|$)", flat, flags=re.IGNORECASE)
    return [" ".join(j.split()) for j in found]


def filters(text: str) -> list[str]:
    """As condições do WHERE, uma por item (separadas pelos AND/OR de fora dos parênteses)."""
    flat = " ".join(text.split())
    match = re.search(r"\bwhere\b(.+?)(?=\b(?:group\s+by|order\s+by|having|limit|union)\b|;|$)", flat,
                      flags=re.IGNORECASE)
    if not match:
        return []
    out: list[str] = []
    depth, current = 0, []
    for word in match.group(1).split():
        if depth == 0 and word.upper() in ("AND", "OR") and current:
            out.append(" ".join(current))
            current = [word.upper()]
        else:
            current.append(word)
        depth += word.count("(") - word.count(")")
    if current:
        out.append(" ".join(current))
    return out


def ordering(text: str) -> str:
    flat = " ".join(text.split())
    match = re.search(r"\border\s+by\s+(.+?)(?=\b(?:limit|offset)\b|;|$)", flat, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def grouping(text: str) -> str:
    flat = " ".join(text.split())
    match = re.search(r"\bgroup\s+by\s+(.+?)(?=\b(?:having|order\s+by|limit)\b|;|$)", flat, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


# --- JSON -------------------------------------------------------------------------

def looks_like_json(text: str) -> bool:
    """Começa com { ou [ e tem pares "chave": valor."""
    flat = text.strip()
    return bool(flat) and flat[0] in "{[" and bool(re.search(r"[\"'“”]?\w[\w\s.-]*[\"'“”]?\s*:", flat))


def fix_json(text: str) -> str:
    """Conserta o que o OCR e os logs estragam: aspas curvas, aspas simples, vírgula sobrando
    antes de } ou ], True/False/None do Python e chaves sem aspas."""
    text = re.sub(r"[“”„]", '"', text)
    text = re.sub(r"[‘’´`]", "'", text)
    if "'" in text and '"' not in text:
        text = text.replace("'", '"')
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    text = re.sub(r"\bNone\b", "null", text)
    text = re.sub(r"([{,]\s*)([A-Za-z_][\w-]*)(\s*:)", r'\1"\2"\3', text)  # chave sem aspas
    return text


@dataclass
class JsonReading:
    value: object = None
    text: str = ""  # formatado (ou o texto consertado, se não deu para ler)
    error: str = ""  # "linha 3, coluna 14: falta uma vírgula" quando inválido
    keys: int = 0
    items: int = 0  # elementos em listas
    depth: int = 0


_JSON_ERRORS = {
    "Expecting ',' delimiter": "falta uma vírgula",
    "Expecting ':' delimiter": "falta dois-pontos",
    "Expecting property name enclosed in double quotes": "chave sem aspas",
    "Expecting value": "falta um valor",
    "Unterminated string starting at": "texto sem aspas no fim",
    "Extra data": "sobrou texto depois do fim",
}


def read_json(text: str) -> JsonReading:
    fixed = fix_json(text.strip())
    try:
        value = json.loads(fixed)
    except json.JSONDecodeError as exc:
        reason = _JSON_ERRORS.get(exc.msg, exc.msg)
        return JsonReading(text=fixed, error=f"linha {exc.lineno}, coluna {exc.colno}: {reason}")
    out = JsonReading(value, json.dumps(value, indent=2, ensure_ascii=False))

    def walk(node, level: int) -> None:
        out.depth = max(out.depth, level)
        if isinstance(node, dict):
            out.keys += len(node)
            for child in node.values():
                walk(child, level + 1)
        elif isinstance(node, list):
            out.items += len(node)
            for child in node:
                walk(child, level + 1)

    walk(value, 0)
    return out


class JsonHighlighter(QSyntaxHighlighter):
    """Cores do JSON: chaves, textos, números e true/false/null."""

    def __init__(self, document):
        super().__init__(document)

        def fmt(color: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.DemiBold)
            return f

        self._rules = [
            (QRegularExpression(r'"(?:[^"\\]|\\.)*"'), fmt("#9a5b00")),
            (QRegularExpression(r"-?\b\d+(\.\d+)?([eE][+-]?\d+)?\b"), fmt("#1c6fb8")),
            (QRegularExpression(r"\b(true|false|null)\b"), fmt(theme.REC, True)),
            (QRegularExpression(r'"(?:[^"\\]|\\.)*"(?=\s*:)'), fmt(theme.S600, True)),
        ]

    def highlightBlock(self, text: str) -> None:
        for pattern, form in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), form)


# --- resumo da tabela ----------------------------------------------------------------

def number(value: str, comma_decimal: bool = True) -> float | None:
    """Número de uma célula: 1240.50, 1.240,50 (com vírgula decimal), R$ 7, 12%. None se não for."""
    v = re.sub(r"^(R\$|US\$|\$)\s*", "", value.strip()).rstrip("%").strip()
    if not v:
        return None
    if comma_decimal and re.fullmatch(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?", v):
        v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}")


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


def column_stats(rows: list[list[str]], header: bool = True, comma_decimal: bool = True) -> list[ColumnStats]:
    """Resumo de cada coluna da grade: o que tem nela e, se for número, as contas."""
    names = columns(rows, header)
    data = _data(rows, header)
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
        if kind == "número" and numbers:
            stats.sum = sum(numbers)
            stats.mean = stats.sum / len(numbers)
            stats.min, stats.max = min(numbers), max(numbers)
        out.append(stats)
    return out


def brl(value: float) -> str:
    """1240.5 -> "1.240,50"; inteiros ficam sem casas."""
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def analysis_tab(result) -> str | None:
    """Aba da Análise para o que foi lido: "query", "json", "table" ou None (texto comum)."""
    if result is None or not result.words:
        return None
    if looks_like_json(result.text):
        return "json"
    if looks_like_sql(result.text):
        return "query"
    if looks_like_table(table_rows(result.words)):
        return "table"
    return None
