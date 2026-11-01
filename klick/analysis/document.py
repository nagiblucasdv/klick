"""JSON lido de um print (log, resposta de API): validação com o erro em português, o tamanho, o
caminho de cada campo e a lista de objetos que vira tabela."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_ERRORS = {
    "Expecting ',' delimiter": "falta uma vírgula",
    "Expecting ':' delimiter": "falta dois-pontos",
    "Expecting property name enclosed in double quotes": "chave sem aspas",
    "Expecting value": "falta um valor",
    "Unterminated string starting at": "texto sem aspas no fim",
    "Extra data": "sobrou texto depois do fim",
    "Invalid control character at": "quebra de linha dentro de um texto",
}


def looks_like_json(text: str) -> bool:
    """Começa com { ou [ e tem pares "chave": valor (ou é uma lista de valores)."""
    flat = text.strip()
    if not flat or flat[0] not in "{[":
        return False
    return bool(re.search(r"[\"'“”]?[\w$-][\w\s.$-]*[\"'“”]?\s*:", flat)) or flat[0] == "[" and flat.rstrip()[-1:] == "]"


@dataclass
class Reading:
    value: object = None
    error: str = ""  # "linha 3, coluna 14: falta uma vírgula"
    line: int = 0  # linha do erro (1 = primeira)
    keys: int = 0
    items: int = 0  # elementos somando todas as listas
    depth: int = 0
    nulls: int = 0

    @property
    def ok(self) -> bool:
        return not self.error


def read(text: str) -> Reading:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return Reading(error=f"linha {exc.lineno}, coluna {exc.colno}: {_ERRORS.get(exc.msg, exc.msg)}", line=exc.lineno)
    out = Reading(value)

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
        elif node is None:
            out.nulls += 1

    walk(value, 0)
    return out


def pretty(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def path(parts: list) -> str:
    """["itens", 0, "cod"] -> "itens[0].cod" (chaves com espaço ou ponto vão entre colchetes)."""
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        elif re.fullmatch(r"[A-Za-z_$][\w$]*", part):
            out += f".{part}" if out else part
        else:
            out += f"[{json.dumps(part, ensure_ascii=False)}]"
    return out or "$"


def type_name(value) -> str:
    if isinstance(value, dict):
        return f"objeto ({len(value)} chave{'s' if len(value) != 1 else ''})"
    if isinstance(value, list):
        return f"lista ({len(value)} ite{'ns' if len(value) != 1 else 'm'})"
    if value is None:
        return "nulo"
    if isinstance(value, bool):
        return "sim/não"
    if isinstance(value, (int, float)):
        return "número"
    return "texto"


def records(value, parts: list | None = None) -> tuple[list, list[dict]] | None:
    """A maior lista de objetos dentro do JSON (ela mesma, ou numa chave como "itens"), com o caminho."""
    parts = parts or []
    best = None
    if isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
        best = (parts, value)
    children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, child in children:
        found = records(child, [*parts, key])
        if found and (best is None or len(found[1]) > len(best[1])):
            best = found
    return best


def to_rows(objects: list[dict]) -> list[list[str]]:
    """Lista de objetos -> grade: as chaves (na ordem em que aparecem) no cabeçalho, um objeto por linha."""
    names: list[str] = []
    for obj in objects:
        for key in obj:
            if key not in names:
                names.append(key)

    def cell(v) -> str:
        if v is None:
            return ""
        if isinstance(v, (dict, list)):
            return compact(v)
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    return [names, *[[cell(obj.get(k)) for k in names] for obj in objects]]


def describe(reading: Reading) -> str:
    if not reading.ok:
        return f"JSON inválido ({reading.error}). Corrija no texto e a leitura atualiza sozinha."
    value = reading.value
    found = records(value)
    if isinstance(value, list):
        head = f"Lista com {len(value)} ite{'ns' if len(value) != 1 else 'm'}"
    elif isinstance(value, dict):
        head = f"Objeto com {len(value)} chave{'s' if len(value) != 1 else ''}"
    else:
        return f"Um valor só: {compact(value)[:60]}."
    extra = []
    if reading.depth > 1:
        extra.append(f"{reading.depth} níveis")
    if found and found[0]:
        names = to_rows(found[1])[0]
        extra.append(f"a lista {path(found[0])} tem {len(found[1])} objeto{'s' if len(found[1]) != 1 else ''} com "
                     f"{', '.join(names[:4])}"
                     + ("…" if len(names) > 4 else ""))
    elif found:
        names = to_rows(found[1])[0]
        extra.append(f"cada um com {', '.join(names[:4])}" + ("…" if len(names) > 4 else ""))
    if reading.nulls:
        extra.append(f"{reading.nulls} campo{'s' if reading.nulls != 1 else ''} nulo{'s' if reading.nulls != 1 else ''}")
    return head + (": " + "; ".join(extra) if extra else "") + "."
