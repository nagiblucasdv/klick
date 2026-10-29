"""Extra "SQL e tabelas" da leitura (ligado por padrão; desliga nas configurações).

- Consulta SQL no print: conserta erros típicos do OCR e formata (palavras-chave em
  maiúsculas, uma cláusula por linha). Na leitura aparece o botão SQL.
- Grade de resultado no print (SSMS, DBeaver, planilha): vira texto para colar no Excel,
  CSV ou INSERTs. Na leitura aparece o botão Tabela.
"""

from __future__ import annotations

import re

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

    def __init__(self, document, dark: bool):
        super().__init__(document)

        def fmt(color: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.DemiBold)
            return f

        keyword = theme.S400 if dark else theme.S600
        self._rules = [
            (QRegularExpression(r"\b(" + "|".join(KEYWORDS) + r")\b",
                                QRegularExpression.PatternOption.CaseInsensitiveOption), fmt(keyword, True)),
            (QRegularExpression(r"\b\d+(\.\d+)?\b"), fmt(theme.CYAN if dark else "#0077a3")),
            (QRegularExpression(r"'[^']*'"), fmt(theme.OK if dark else "#1e7a45")),
            (QRegularExpression(r"--[^\n]*"), fmt(theme.G400)),
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


def _literal(value: str) -> str:
    value = value.strip()
    if not value or value.upper() == "NULL":
        return "NULL"
    if re.fullmatch(r"-?\d+(\.\d+)?", value):
        return value
    return "'" + value.replace("'", "''") + "'"


def to_insert(rows: list[list[str]], table: str = "tabela") -> str:
    """A primeira linha vira o nome das colunas; cada linha seguinte, um INSERT."""
    if len(rows) < 2:
        return ""
    columns = ", ".join(_column(c, i) for i, c in enumerate(rows[0]))
    return "\n".join(f"INSERT INTO {table} ({columns}) VALUES ({', '.join(_literal(v) for v in r)});"
                     for r in rows[1:] if any(r))
