"""Texto remontado pela posição das palavras na imagem: linhas visuais e a indentação do print.

Os motores de OCR devolvem "linhas" que nem sempre são as do print (o RapidOCR quebra uma linha
de código em pedaços quando há espaço grande no meio). Agrupar as palavras pela altura refaz as
linhas de verdade; a distância até a margem, medida em larguras de caractere, vira a indentação.
"""

from __future__ import annotations

from statistics import median


def visual_lines(words) -> list[list]:
    """Palavras agrupadas em linhas (centro na mesma faixa de altura), cada linha da esquerda para a direita."""
    words = [w for w in words if w.text.strip()]
    if not words:
        return []
    height = median(w.rect.height() for w in words)
    lines: list[list] = []
    centers: list[float] = []
    for w in sorted(words, key=lambda w: w.rect.center().y()):
        y = w.rect.center().y()
        if lines and abs(y - centers[-1]) < height * 0.55:
            lines[-1].append(w)
            centers[-1] = sum(x.rect.center().y() for x in lines[-1]) / len(lines[-1])
        else:
            lines.append([w])
            centers.append(y)
    for line in lines:
        line.sort(key=lambda w: w.rect.left())
    return lines


def char_width(words) -> float:
    widths = [w.rect.width() / len(w.text) for w in words if len(w.text.strip()) >= 2]
    return max(median(widths), 1.0) if widths else 8.0


def layout_text(result) -> str:
    """O texto como aparece no print: uma linha por linha visual, com a indentação de cada uma."""
    words = [w for w in (result.words if result is not None else ()) if w.text.strip()]
    if not words:
        return result.text if result is not None else ""
    lines = visual_lines(words)
    width = char_width(words)
    margin = min(line[0].rect.left() for line in lines)
    out = []
    for line in lines:
        indent = round((line[0].rect.left() - margin) / width)
        out.append(" " * min(indent, 60) + " ".join(w.text for w in line))
    return "\n".join(out)
