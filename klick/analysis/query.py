"""Consulta SQL: as partes (tabelas, colunas, junções, filtros, agrupamento, ordem), a conferência do
que costuma dar errado e uma frase em português dizendo o que a consulta faz.

As palavras-chave só contam no nível de fora: o que está entre aspas, em comentário ou entre
parênteses (subconsulta, função) é mascarado antes de procurar as cláusulas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from klick.analysis.fixes import SQL_KEYWORDS

STATEMENTS = ("select", "with", "insert", "update", "delete", "create", "alter", "drop")
_CLAUSE = re.compile(
    r"\b(?:(left|right|full)(?:\s+outer)?\s+join|(inner|cross|natural)\s+join|join|select|from|where|group\s+by|"
    r"having|order\s+by|limit|offset|fetch|union(?:\s+all)?|set|values|returning|update|delete\s+from|"
    r"insert\s+into|with)\b", re.IGNORECASE)
_NAME = r"[\w$#]+(?:\.[\w$#]+)*|\"[^\"]+\"|\[[^\]]+\]|`[^`]+`"
_TABLE = re.compile(rf"^\s*({_NAME})(?:\s+(?:as\s+)?([A-Za-z_]\w*))?", re.IGNORECASE)
_CLUES = [r"\bselect\b.+\bfrom\b", r"\bupdate\b.+\bset\b", r"\binsert\s+into\b", r"\bdelete\s+from\b",
          r"\bcreate\s+(table|view|index)\b", r"\bwhere\b", r"\bjoin\b.+\bon\b", r"\bgroup\s+by\b",
          r"\border\s+by\b", r"\bvalues\s*\("]
AGGREGATES = {"sum": "a soma de", "count": "a contagem de", "avg": "a média de", "max": "o maior", "min": "o menor"}


def looks_like_sql(text: str) -> bool:
    """Começa com um comando (SELECT, UPDATE…) que tem a parte que o acompanha, ou tem duas pistas de SQL."""
    flat = " ".join(_mask(text).split()).lower()
    first = re.match(r"\s*(\w+)", flat)
    if first and first.group(1) in STATEMENTS:
        follow = {"select": r"\bfrom\b|^select\s+[\w'(]", "with": r"\bselect\b", "insert": r"\binto\b",
                  "update": r"\bset\b", "delete": r"\bfrom\b", "create": r"\b(table|view|index|function)\b",
                  "alter": r"\btable\b", "drop": r"\b(table|view|index)\b"}[first.group(1)]
        if re.search(follow, flat):
            return True
    return sum(bool(re.search(clue, flat)) for clue in _CLUES) >= 2


def _mask(text: str) -> str:
    """Mesmo tamanho do texto, com textos entre aspas e comentários trocados por espaço."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        if text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
        elif text[i] in "'\"`":
            quote = text[i]
            j = i + 1
            while j < n and not (text[j] == quote and not (j + 1 < n and text[j + 1] == quote and quote == "'")):
                j += 2 if text[j] == quote else 1
            j = min(j + 1, n)
            for k in range(i + 1, max(i + 1, j - 1)):
                out[k] = " "
            i = j
            continue
        else:
            i += 1
            continue
        for k in range(i, j):
            if out[k] != "\n":
                out[k] = " "
        i = j
    return "".join(out)


def _flat_mask(text: str) -> str:
    """_mask e também o que está entre parênteses, para achar só o que está no nível de fora."""
    out = list(_mask(text))
    depth = 0
    for i, ch in enumerate(out):
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            continue
        if depth:
            out[i] = " "
    return "".join(out)


def split_top(text: str, sep: str = ",") -> list[str]:
    """Divide pelo separador só no nível de fora (fora de parênteses e aspas)."""
    masked = _flat_mask(text)
    parts, start = [], 0
    for i, ch in enumerate(masked):
        if ch == sep:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [" ".join(p.split()) for p in parts if p.strip()]


@dataclass
class Join:
    kind: str  # "LEFT JOIN", "JOIN"…
    table: str
    alias: str
    condition: str  # o que vem depois do ON (ou USING)


@dataclass
class Query:
    text: str
    kind: str = ""  # SELECT, UPDATE, INSERT, DELETE, CREATE…
    tables: list[tuple[str, str]] = field(default_factory=list)  # (tabela, apelido) do FROM / UPDATE / INTO
    columns: list[str] = field(default_factory=list)  # SELECT ou INSERT (colunas)
    joins: list[Join] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)  # condições do WHERE, com o AND/OR que as liga
    where: str = ""
    group: list[str] = field(default_factory=list)
    order: list[tuple[str, bool]] = field(default_factory=list)  # (expressão, decrescente)
    limit: str = ""
    assignments: list[tuple[str, str]] = field(default_factory=list)  # SET coluna = valor
    values: list[int] = field(default_factory=list)  # quantos valores em cada linha do VALUES
    distinct: bool = False

    def alias_map(self) -> dict[str, str]:
        """Apelido (ou o próprio nome) -> tabela."""
        out = {}
        for table, alias in [*self.tables, *((j.table, j.alias) for j in self.joins)]:
            out[(alias or table.split(".")[-1]).lower()] = table
        return out


def _table(text: str) -> tuple[str, str]:
    m = _TABLE.match(text)
    if not m:
        return " ".join(text.split()), ""
    alias = m.group(2) or ""
    if alias.upper() in SQL_KEYWORDS:
        alias = ""
    return m.group(1), alias


def _no_comments(text: str) -> str:
    """O texto com os comentários trocados por espaço (textos entre aspas ficam)."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            j = text.find(ch, i + 1)
            i = n if j < 0 else j + 1
            continue
        if text.startswith("--", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
        else:
            i += 1
            continue
        for k in range(i, end):
            if out[k] != "\n":
                out[k] = " "
        i = end
    return "".join(out)


def _clauses(text: str) -> list[tuple[str, str]]:
    """[(cláusula, conteúdo)] no nível de fora, na ordem em que aparecem (sem os comentários)."""
    text = _no_comments(text)
    masked = _flat_mask(text)
    marks = [(m.start(), m.end(), " ".join(m.group(0).upper().split())) for m in _CLAUSE.finditer(masked)]
    out = []
    for k, (start, end, name) in enumerate(marks):
        stop = marks[k + 1][0] if k + 1 < len(marks) else len(text)
        out.append((name, text[end:stop].strip().rstrip(";").strip()))
    return out


def conditions(text: str) -> list[str]:
    """Condições separadas pelos AND/OR de fora: ["a = 1", "AND b > 2"]. O AND do BETWEEN fica junto."""
    masked = _flat_mask(text)
    out, start = [], 0
    for m in re.finditer(r"\b(and|or)\b", masked, re.IGNORECASE):
        before = masked[start:m.start()]
        if m.group(1).lower() == "and" and re.search(r"\bbetween\s+\S+\s*$", before, re.IGNORECASE):
            continue
        piece = " ".join(text[start:m.start()].split())
        if piece:
            out.append(piece)
        start = m.start()
    last = " ".join(text[start:].split())
    if last:
        out.append(last)
    return [re.sub(r"^(and|or)\b", lambda m: m.group(1).upper(), c, flags=re.IGNORECASE) for c in out]


def parse(text: str) -> Query:
    q = Query(text)
    first = re.match(r"\s*(\w+)", _mask(text))
    q.kind = first.group(1).upper() if first and first.group(1).lower() in STATEMENTS else ""
    for name, body in _clauses(text):
        if name == "SELECT":
            if (distinct := re.match(r"\s*distinct\b", body, re.IGNORECASE)) is not None:
                q.distinct, body = True, body[distinct.end():]
            if (top := re.match(r"^\s*top\s+(\d+)\s+", body, re.IGNORECASE)) is not None:
                q.limit, body = top.group(1), body[top.end():]
            q.columns = split_top(body)
        elif name == "FROM":
            q.tables = [_table(part) for part in split_top(body)]
        elif name.endswith("JOIN"):
            m = re.search(r"\b(on|using)\b", _flat_mask(body), re.IGNORECASE)
            target, condition = (body[:m.start()], body[m.end():]) if m else (body, "")
            table, alias = _table(target)
            q.joins.append(Join(name, table, alias, " ".join(condition.split())))
        elif name == "WHERE":
            q.where = " ".join(body.split())
            q.filters = conditions(body)
        elif name == "GROUP BY":
            q.group = split_top(body)
        elif name == "ORDER BY":
            for part in split_top(body):
                desc = bool(re.search(r"\bdesc\b", part, re.IGNORECASE))
                q.order.append((re.sub(r"\s+(asc|desc)\b.*$", "", part, flags=re.IGNORECASE), desc))
        elif name == "LIMIT":
            q.limit = body.split()[0] if body.split() else ""
        elif name == "FETCH":
            m = re.search(r"\d+", body)
            q.limit = m.group() if m else q.limit
        elif name == "UPDATE":
            q.tables = [_table(body)]
        elif name == "SET":
            for part in split_top(body):
                col, _, value = part.partition("=")
                q.assignments.append((col.strip(), value.strip()))
        elif name == "DELETE FROM":
            q.tables = [_table(body)]
        elif name == "INSERT INTO":
            m = re.match(rf"\s*({_NAME})\s*(\((.*)\))?", body, re.DOTALL)
            if m:
                q.tables = [(m.group(1), "")]
                q.columns = split_top(m.group(3) or "")
        elif name == "VALUES":
            q.values = [len(split_top(row)) for row in re.findall(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)", body)]
    return q


# --- conferência ---------------------------------------------------------------------

@dataclass(frozen=True)
class Check:
    level: str  # "danger", "warn" ou "ok"
    text: str


def checks(q: Query, unclosed: str = "") -> list[Check]:
    """O que pode estar errado na consulta, do mais grave para o menos. Sem nada, um "ok"."""
    out: list[Check] = []
    masked = _mask(q.text)
    table = q.tables[0][0] if q.tables else "a tabela"
    if q.kind in ("UPDATE", "DELETE") and not q.where:
        verb = "Altera" if q.kind == "UPDATE" else "Apaga"
        out.append(Check("danger", f"{q.kind} sem WHERE: {verb.lower()} todas as linhas de {table}."))
    if unclosed:
        out.append(Check("danger", f"Uma aspa {unclosed} abre e não fecha: o resto vira texto."))
    opened, closed = masked.count("("), masked.count(")")
    if opened != closed:
        missing = "fechar" if opened > closed else "abrir"
        out.append(Check("danger", f"Parênteses desequilibrados: falta {missing} {abs(opened - closed)}."))
    if re.search(r"(?<![<>!])(=|<>|!=)\s*null\b", masked, re.IGNORECASE):
        out.append(Check("warn", "Comparação com NULL usando = ou <>: nunca é verdadeira. Use IS NULL ou IS NOT NULL."))
    for j in q.joins:
        if not j.condition and not re.match(r"(CROSS|NATURAL)", j.kind):
            out.append(Check("warn", f"{j.kind} {j.table} sem ON: junta cada linha com todas as outras."))
    if q.columns and re.search(r",\s*$", re.split(r"\bfrom\b", q.text, flags=re.IGNORECASE)[0]) and q.kind == "SELECT":
        out.append(Check("danger", "Vírgula sobrando antes do FROM."))
    for j in q.joins:
        if not j.kind.startswith("LEFT"):
            continue
        name = (j.alias or j.table.split(".")[-1]).lower()
        for cond in q.filters:
            body = re.sub(r"^(AND|OR)\s+", "", cond)
            if re.search(rf"\b{re.escape(name)}\.", body, re.IGNORECASE) and not re.search(r"\bis\s+(not\s+)?null\b",
                                                                                          body, re.IGNORECASE):
                out.append(Check("warn", f"O filtro {body} no WHERE transforma o LEFT JOIN em JOIN comum: linhas sem "
                                         f"{j.table} somem. Para mantê-las, passe a condição para o ON."))
                break
    if q.kind == "INSERT" and q.columns and q.values and any(v != len(q.columns) for v in q.values):
        out.append(Check("danger", f"INSERT com {len(q.columns)} colunas e {q.values[0]} valores."))
    if not out:
        out.append(Check("ok", "Nada estranho: parênteses e aspas fechados, filtros e junções completos."))
    return out


# --- frase em português -----------------------------------------------------------------

def _plain_column(col: str) -> str:
    """"SUM(p.valor) AS total" -> "a soma de p.valor (total)"."""
    alias = ""
    m = re.match(r"(.*?)\s+(?:as\s+)?([A-Za-z_]\w*)$", col, re.IGNORECASE)
    if m and "(" in m.group(1) and m.group(1).rstrip().endswith(")"):
        col, alias = m.group(1).strip(), m.group(2)
    agg = re.match(r"(\w+)\s*\(\s*(distinct\s+)?(.*)\)$", col, re.IGNORECASE)
    if agg and agg.group(1).lower() in AGGREGATES:
        inner = agg.group(3).strip()
        if agg.group(1).lower() == "count":
            if inner == "*":
                text = "a contagem de linhas"
            else:
                text = f"quantos {inner} diferentes" if agg.group(2) else f"a contagem de {inner}"
        else:
            text = f"{AGGREGATES[agg.group(1).lower()]} {inner}"
        return f"{text} ({alias})" if alias else text
    return col


def _join_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


def describe(q: Query) -> str:
    """O que a consulta faz, numa frase."""
    table = q.tables[0][0] if q.tables else ""
    where = f" onde {q.where}" if q.where else ""
    if q.kind == "UPDATE":
        cols = _join_list([c for c, _ in q.assignments]) if q.assignments else "colunas"
        return (f"Altera {cols} em {table}{where}." if q.where
                else f"Altera {cols} em TODAS as linhas de {table}.")
    if q.kind == "DELETE":
        return f"Apaga de {table} as linhas{where}." if q.where else f"Apaga TODAS as linhas de {table}."
    if q.kind == "INSERT":
        rows = len(q.values) or 1
        cols = f" ({_join_list(q.columns)})" if q.columns else ""
        return f"Insere {rows} linha{'s' if rows != 1 else ''} em {table}{cols}."
    if q.kind == "CREATE":
        m = re.match(r"\s*create\s+(?:or\s+replace\s+)?(\w+)\s+(?:if\s+not\s+exists\s+)?([\w.\"]+)", q.text, re.I)
        return f"Cria {m.group(1).lower()} {m.group(2)}." if m else "Cria um objeto no banco."
    if q.kind in ("ALTER", "DROP"):
        verb = "Altera" if q.kind == "ALTER" else "Apaga"
        m = re.match(r"\s*\w+\s+(\w+)\s+(?:if\s+exists\s+)?([\w.\"]+)", q.text, re.I)
        return f"{verb} {m.group(1).lower()} {m.group(2)}." if m else f"{verb} um objeto do banco."
    if q.kind not in ("SELECT", "WITH"):
        return "Comando SQL."
    if q.columns == ["*"]:
        what = "todas as colunas"
    else:
        cols = [_plain_column(c) for c in q.columns]
        what = _join_list(cols[:4]) + (f" e mais {len(cols) - 4}" if len(cols) > 4 else "") if cols else "dados"
    if q.distinct:
        what += ", sem repetir"
    source = f" de {table}" if table else ""
    if q.joins:
        source += " junto com " + _join_list([f"{j.table} ({j.kind.lower()})" for j in q.joins])
    parts = [f"Busca {what}{source}"]
    if q.filters:
        parts.append(f"só onde {q.where}" if len(q.filters) <= 2 else f"com {len(q.filters)} filtros")
    if q.group:
        parts.append(f"uma linha por {_join_list(q.group)}")
    if q.order:
        expr, desc = q.order[0]
        parts.append(f"do maior {expr} para o menor" if desc else f"em ordem de {expr}")
    if q.limit:
        parts.append(f"no máximo {q.limit} linhas")
    return ", ".join(parts) + "."


# --- ajudas para UPDATE e DELETE ----------------------------------------------------------

def preview_select(q: Query) -> str:
    """As linhas que o UPDATE ou o DELETE vão mudar, para conferir antes de rodar."""
    if q.kind not in ("UPDATE", "DELETE") or not q.tables or not q.where:
        return ""
    table, alias = q.tables[0]
    cols = "*"
    if q.kind == "UPDATE" and q.assignments:
        prefix = f"{alias}." if alias else ""
        cols = ", ".join(c if "." in c else prefix + c for c, _ in q.assignments)
    return f"SELECT {cols}\nFROM {table}{' ' + alias if alias else ''}\nWHERE {q.where};"


def backup_select(q: Query, today: date | None = None) -> str:
    """Cópia das linhas que vão mudar, numa tabela de backup com a data (para voltar se der errado)."""
    if q.kind not in ("UPDATE", "DELETE") or not q.tables or not q.where:
        return ""
    table, alias = q.tables[0]
    name = table.split(".")[-1].strip('"[]`')
    stamp = (today or date.today()).strftime("%Y%m%d")
    return f"CREATE TABLE {name}_bkp_{stamp} AS\nSELECT *\nFROM {table}{' ' + alias if alias else ''}\nWHERE {q.where};"


# --- formatação -------------------------------------------------------------------------

def format_sql(text: str) -> str:
    """Uma cláusula por linha, palavras-chave em maiúsculas. Comentários de linha viram /* */ antes, para
    não engolirem o resto quando o texto é juntado numa linha só."""
    try:
        import sqlparse
    except ImportError:
        return text
    flat = " ".join(_block_comments(text).split())
    out = sqlparse.format(flat, reindent=True, keyword_case="upper", indent_width=4).strip()
    masked = _mask(out)  # funções em maiúsculas também, fora de texto e comentário
    for m in reversed(list(_FUNCTIONS.finditer(masked))):
        out = out[:m.start(1)] + m.group(1).upper() + out[m.end(1):]
    return out


_FUNCTIONS = re.compile(r"\b(sum|count|avg|min|max|coalesce|ifnull|nullif|cast|upper|lower|trim|substring|substr|"
                        r"concat|round|now|date|extract|to_char|to_date|length|replace|exists)\s*\(", re.IGNORECASE)


def _block_comments(text: str) -> str:
    """"-- nota" vira "/* nota */" (fora de texto entre aspas)."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            j = i + 1
            while j < n and text[j] != ch:
                j += 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(f"/* {text[i + 2:j].strip()} */")
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)
