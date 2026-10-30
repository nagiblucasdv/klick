from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QGuiApplication, QImage

from klick import sql
from klick.ocr import OcrResult, Word
from klick.sql_ui import AnalysisWindow


def image() -> QImage:
    img = QImage(400, 200, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    return img


def grid_result() -> OcrResult:
    cells = [["Cod", "Descrição", "Preço"], ["1", "Arroz", "1.240,50"], ["2", "Feijão", "7"]]
    words = []
    for r, row in enumerate(cells):
        for c, text in enumerate(row):
            words.append(Word(text, QRectF(10 + c * 150, 10 + r * 30, 9 * len(text), 16), r * 10 + c))
    return OcrResult(tuple(words), "RapidOCR")


def query_result() -> OcrResult:
    lines = ["select id, nome FR0M clientes c", "join pedidos p on p.cliente = c.id where p.total > 10"]
    words = []
    for i, line in enumerate(lines):
        x = 10
        for part in line.split():
            words.append(Word(part, QRectF(x, 10 + i * 24, 8 * len(part), 16), i))
            x += 8 * len(part) + 6
    return OcrResult(tuple(words), "RapidOCR", tuple(lines))


def test_query_tab_formats_and_lists_tables(qapp):
    window = AnalysisWindow(image(), query_result(), refine=False)
    assert window.tabs.value == "query"
    text = window.query.toPlainText()
    assert text.startswith("SELECT") and "FROM clientes" in text
    assert window.kind.text() == "SELECT"
    assert window.tables.text().split() == ["clientes", "pedidos"]
    window._copy()
    assert QGuiApplication.clipboard().text() == text
    window.close()


def test_grid_opens_in_table_tab_with_insert_preview(qapp):
    window = AnalysisWindow(image(), grid_result(), refine=False)
    assert window.tabs.value == "table"  # é grade, não consulta
    window.table_name.setText("produtos")
    assert window.output.toPlainText().splitlines()[0] == \
        "INSERT INTO produtos (cod, descricao, preco) VALUES (1, 'Arroz', 1240.50);"
    window.close()


def test_update_uses_chosen_key_and_edited_cells(qapp):
    window = AnalysisWindow(image(), grid_result(), refine=False)
    window.table_name.setText("produtos")
    window.format.set_value("update")
    window.key.setCurrentIndex(1)  # WHERE descricao
    window.grid.item(2, 2).setText("8")  # corrigiu uma célula à mão
    lines = window.output.toPlainText().splitlines()
    assert lines[1] == "UPDATE produtos SET cod = 2, preco = 8 WHERE descricao = 'Feijão';"
    window.close()


def test_without_header_and_removing_rows(qapp):
    window = AnalysisWindow(image(), grid_result(), refine=False)
    window.header.setChecked(False)
    window.grid.selectRow(0)
    window._remove_rows()
    assert window.rows()[0][1] == "Arroz"
    assert "INSERT INTO tabela (coluna1, coluna2, coluna3) VALUES (1, 'Arroz', 1240.50);" in window.output.toPlainText()
    window.format.set_value("excel")
    assert window.output.toPlainText() == sql.to_tsv(window.rows())
    window.close()


def test_best_reading_wins_unless_edited(qapp):
    window = AnalysisWindow(image(), grid_result(), refine=False)
    garbage = OcrResult((Word(".o--.", QRectF(0, 0, 10, 10), 0), Word("o", QRectF(20, 0, 5, 10), 0)), "RapidOCR")
    window._on_done(garbage, "")  # leitura pior: fica a que já estava
    assert window.tabs.value == "table" and window.rows()[1][1] == "Arroz"
    window._on_done(query_result(), "")  # leitura mais limpa: troca
    assert window.query.toPlainText().startswith("SELECT")
    window.query.setPlainText("SELECT 1")  # o usuário editou
    longer = OcrResult(query_result().words * 2, "RapidOCR", query_result().lines * 2)
    window._on_done(longer, "")
    assert window.query.toPlainText() == "SELECT 1" and "editou" in window.message.text()
    window.close()


def test_reading_score_prefers_clean_text():
    assert sql.reading_score("join pedidos p on p.codcli = c.codcli") > sql.reading_score(".o--.   d d =  o  opp .")
    assert sql.fix_ocr("select c. codcli from x") == "SELECT c.codcli from x"
