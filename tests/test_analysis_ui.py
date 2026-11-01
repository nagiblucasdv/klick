"""Janela da Análise."""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QGuiApplication, QImage

from klick import config
from klick.analysis import Kind
from klick.analysis.schema import Schema
from klick.analysis_ui import AnalysisWindow
from klick.ocr import OcrResult, Word


def image() -> QImage:
    img = QImage(400, 200, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    return img


def lines_result(lines: list[str], language: str = "RapidOCR") -> OcrResult:
    words = []
    for i, line in enumerate(lines):
        x = 10
        for part in line.split():
            words.append(Word(part, QRectF(x, 10 + i * 24, 8 * len(part), 16), i))
            x += 8 * len(part) + 8
    return OcrResult(tuple(words), language)


def grid_result() -> OcrResult:
    cells = [["Cod", "Descrição", "Preço"], ["1", "Arroz", "1.240,50"], ["2", "Feijão", "7"], ["3", "Café", "1O"]]
    words = [Word(text, QRectF(10 + c * 150, 10 + r * 30, 9 * len(text), 16), r)
             for r, row in enumerate(cells) for c, text in enumerate(row)]
    return OcrResult(tuple(words), "RapidOCR")


QUERY = ["select c.codcli, c.nome FR0M clientes c", "left join pedidos p on p.codcli = c. codcli",
         "where p.valor > 10"]


def test_sql_opens_formatted_with_fixes_marked_and_undoable(qapp):
    window = AnalysisWindow(image(), lines_result(QUERY), refine=False)
    assert window._kind is Kind.SQL and window.title.text() == "Consulta SQL"
    text = window.sql.toPlainText()
    assert text.startswith("SELECT c.codcli,") and "\nFROM clientes c" in text and "c.codcli" in text
    assert [(f.before, f.after) for f in window._sql_fixes] == [("FR0M", "FROM"), ("c. codcli", "c.codcli")]
    assert "LEFT JOIN" in window.sql_checks.findChild(type(window.title)).text()  # o WHERE em p anula o LEFT JOIN
    assert window.sql_verdict.text.text().startswith("Busca c.codcli e c.nome de clientes junto com pedidos")
    window.sql_fix_list.undo.emit(window._sql_fixes[0].number)  # desfaz o FR0M -> FROM
    assert "FR0M" in window.sql.toPlainText() and [f.before for f in window._sql_fixes] == ["c. codcli"]
    window.sql_view.set_value("raw")
    assert window.sql.toPlainText().splitlines()[0] == "select c.codcli, c.nome FR0M clientes c"
    window._copy()
    assert QGuiApplication.clipboard().text() == window.sql.toPlainText()
    window.close()


def test_update_without_where_and_helpers(qapp):
    danger = AnalysisWindow(image(), lines_result(["update clientes set uf = 'SP'"]), refine=False)
    labels = [w.text() for w in danger.sql_checks.findChildren(type(danger.title))]
    assert any("UPDATE sem WHERE" in t for t in labels) and not danger.preview.isVisibleTo(danger)
    danger.close()
    window = AnalysisWindow(image(), lines_result(["update clientes c set uf = 'SP' where c.codcli = 5"]), refine=False)
    assert window.preview.isVisibleTo(window)
    window.preview.click()
    assert QGuiApplication.clipboard().text() == "SELECT c.uf\nFROM clientes c\nWHERE c.codcli = 5;"
    window.close()


def test_json_is_formatted_with_tree_and_turns_into_table(qapp):
    result = lines_result(["{'itens': [{'cod': 1, 'nome': 'Arroz'},", "{'cod': 2, 'nome': 'Feijão'}], ok: True}"])
    window = AnalysisWindow(image(), result, refine=False)
    assert window._kind is Kind.JSON and window.json_state.text() == "Válido"
    assert window.json.toPlainText().startswith('{\n  "itens": [')
    assert window.tree.topLevelItemCount() == 2 and window.tree.topLevelItem(0).text(0) == "itens"
    window.tree.itemClicked.emit(window.tree.topLevelItem(0).child(1).child(0), 0)
    assert QGuiApplication.clipboard().text() == "itens[1].cod"
    window.as_table.click()
    assert window._kind is Kind.TABLE and window.rows() == [["cod", "nome"], ["1", "Arroz"], ["2", "Feijão"]]
    assert window.table_name.text() == "itens"
    window._set_kind(Kind.JSON, user=True)
    window.json.setPlainText('{"a": 1 "b": 2}')
    window._update_json()
    assert window.json_state.text() == "Inválido" and "vírgula" in window.json_error.text()
    assert window.json._error_line == 1
    window.close()


def test_table_summary_suspects_and_outputs(qapp):
    window = AnalysisWindow(image(), grid_result(), refine=False)
    assert window._kind is Kind.TABLE and window.header.isChecked()
    assert window._suspected == {(3, 2): "10"}
    assert window.grid.item(3, 2).toolTip() == "O OCR pode ter errado: talvez 10"
    window.apply_suspects.click()
    assert window.rows()[3][2] == "10" and window._suspected == {}
    window.table_name.setText("produtos")
    window.format.set_value("insert")
    assert window.output.toPlainText().splitlines()[0] == \
        "INSERT INTO produtos (cod, descricao, preco) VALUES (1, 'Arroz', 1240.50);"
    window.format.set_value("update")
    window.key.setCurrentIndex(1)
    assert window.output.toPlainText().splitlines()[1] == \
        "UPDATE produtos SET cod = 2, preco = 7 WHERE descricao = 'Feijão';"
    window.format.set_value("markdown")
    assert window.output.toPlainText().splitlines()[0] == "| Cod | Descrição | Preço |"
    assert window.table_verdict.text.text() == "3 linhas e 3 colunas: preco soma 1.257,50."
    window.close()


def test_plain_text_and_read_as(qapp):
    window = AnalysisWindow(image(), lines_result(["Bom dia, o pedido saiu hoje"]), refine=False)
    assert window._kind is Kind.TEXT and "não parece SQL" in window.text_verdict.text.text()
    window.kinds.set_value("sql")
    assert window._kind is Kind.SQL and window._forced
    window.close()


def test_better_reading_wins_unless_edited(qapp):
    window = AnalysisWindow(image(), grid_result(), refine=False)
    garbage = OcrResult((Word(".o--.", QRectF(0, 0, 10, 10), 0), Word("o", QRectF(20, 0, 5, 10), 0)), "RapidOCR")
    window._take(garbage, "")  # leitura pior: fica a que já estava
    assert window._kind is Kind.TABLE and window.rows()[1][1] == "Arroz"
    window._take(lines_result(QUERY * 2), "")  # leitura mais limpa: troca
    assert window._kind is Kind.SQL
    window.sql.setPlainText("SELECT 1")  # o usuário editou
    window._take(lines_result(QUERY * 3), "")
    assert window.sql.toPlainText() == "SELECT 1" and "editou" in window.message.text()
    window.close()


def test_copy_teaches_the_structure_when_enabled(qapp, tmp_path):
    schema = Schema(tmp_path / "estrutura.json")
    window = AnalysisWindow(image(), lines_result(QUERY), refine=False, schema=schema)
    window._copy()
    assert schema.tables == {}  # desligado: não aprende
    config.set_option("structure", True)
    try:
        window._copy()
    finally:
        config.set_option("structure", False)
    assert schema.tables == {"clientes": ["codcli", "nome"], "pedidos": ["codcli", "valor"]}
    window.close()
