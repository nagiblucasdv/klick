"""Motor da Análise: consertos do OCR, SQL, JSON, tabelas e a estrutura aprendida."""

from datetime import date

from PySide6.QtCore import QRectF

from klick.analysis import Kind, detect, document, fixes, grid, query, reading_score
from klick.analysis.layout import layout_text
from klick.analysis.schema import Schema
from klick.ocr import OcrResult, Word

QUERY = """select c.codcli, c.nome, sum(p.valor) total -- soma por cliente
FR0M clientes c
left join pedidos p on p.codcli = c. codcli
where p.data >= ‘2026-10-01’ and c.uf = 'SP' and p.obs like 'Fim. Depois'
group by c.codcli, c.nome
order by total desc;"""


def words_from(lines: list[str], indent: list[int] | None = None) -> OcrResult:
    words = []
    for i, line in enumerate(lines):
        x = 10 + 8 * (indent[i] if indent else 0)
        for part in line.split():
            words.append(Word(part, QRectF(x, 10 + i * 24, 8 * len(part), 16), i))
            x += 8 * len(part) + 8
    return OcrResult(tuple(words), "RapidOCR")


def grid_words(cells: list[list[str]], xs: list[int]) -> list[Word]:
    words = []
    for r, row in enumerate(cells):
        for c, text in enumerate(row):
            x = xs[c]
            for part in text.split():
                words.append(Word(part, QRectF(x, 10 + r * 28, 8 * len(part), 16), r))
                x += 8 * len(part) + 6
    return words


def test_sql_fixes_leave_strings_and_comments_alone():
    out = fixes.fix_sql(QUERY)
    assert [(f.before, f.after) for f in out.fixes] == [("FR0M", "FROM"), ("c. codcli", "c.codcli"),
                                                        ("‘2026-10-01’", "'2026-10-01'")]
    assert "'Fim. Depois'" in out.text and "-- soma por cliente" in out.text  # texto e comentário intactos
    first = out.fixes[0]
    assert out.text[first.start:first.end] == "FROM"
    undone = fixes.fix_sql(QUERY, frozenset({first.number}))
    assert "FR0M clientes" in undone.text and [f.before for f in undone.fixes] == ["c. codcli", "‘2026-10-01’"]


def test_mysql_backticks_survive_and_unclosed_quote_is_reported():
    assert fixes.fix_sql("select `id` from `t`").text == "select `id` from `t`"
    assert fixes.fix_sql("select * from t where a = 'abc").unclosed == "'"


def test_keyword_lookalikes():
    assert fixes.keyword_lookalike("SELEC7") == "SELECT"
    assert fixes.keyword_lookalike("wh3re") == "where"
    assert fixes.keyword_lookalike("AN0") == "AND"
    assert fixes.keyword_lookalike("t1") is None and fixes.keyword_lookalike("1240") is None


def test_query_parts_checks_and_description():
    q = query.parse(fixes.fix_sql(QUERY).text)
    assert q.kind == "SELECT" and q.tables == [("clientes", "c")]
    assert q.columns == ["c.codcli", "c.nome", "sum(p.valor) total"]  # o comentário não entra
    assert [(j.kind, j.table, j.alias, j.condition) for j in q.joins] == [
        ("LEFT JOIN", "pedidos", "p", "p.codcli = c.codcli")]
    assert q.filters == ["p.data >= '2026-10-01'", "AND c.uf = 'SP'", "AND p.obs like 'Fim. Depois'"]
    assert q.group == ["c.codcli", "c.nome"] and q.order == [("total", True)]
    [check] = query.checks(q)
    assert check.level == "warn" and "LEFT JOIN" in check.text and "p.data" in check.text
    text = query.describe(q)
    assert text.startswith("Busca c.codcli, c.nome e a soma de p.valor (total) de clientes junto com pedidos")
    assert text.endswith("do maior total para o menor.")


def test_simple_select_is_sql_and_plain_text_is_not():
    assert query.looks_like_sql("select * from clientes")
    assert query.looks_like_sql("UPDATE t SET a = 1")
    assert not query.looks_like_sql("Selecione a área e depois clique em salvar")


def test_dangerous_and_broken_queries():
    assert query.checks(query.parse("delete from pedidos"))[0].level == "danger"
    levels = {c.text.split(":")[0]: c.level for c in query.checks(query.parse("select a from t where x = null and (b = 1"))}
    assert levels == {"Parênteses desequilibrados": "danger", "Comparação com NULL usando = ou <>": "warn"}
    assert "3 valores" in query.checks(query.parse("insert into t (a, b) values (1, 2, 3)"))[0].text
    assert query.checks(query.parse("select a, from t"))[0].text == "Vírgula sobrando antes do FROM."
    assert query.checks(query.parse("select * from a join b"))[0].level == "warn"
    assert query.checks(query.parse("select * from a where x between 1 and 2"))[0].level == "ok"


def test_update_helpers():
    q = query.parse("update clientes c set nome = 'x', uf = 'RJ' where c.codcli = 5")
    assert query.describe(q) == "Altera nome e uf em clientes onde c.codcli = 5."
    assert query.preview_select(q) == "SELECT c.nome, c.uf\nFROM clientes c\nWHERE c.codcli = 5;"
    assert query.backup_select(q, date(2026, 10, 31)).startswith("CREATE TABLE clientes_bkp_20261031 AS\nSELECT *")
    assert query.preview_select(query.parse("update t set a = 1")) == ""  # sem WHERE não há o que conferir


def test_format_keeps_comments_and_uppercases_functions():
    out = query.format_sql("select sum(v) total -- nota\nfrom t where obs = 'sum(1) -- x'")
    assert out.splitlines() == ["SELECT SUM(v) total /* nota */", "FROM t", "WHERE obs = 'sum(1) -- x'"]


def test_layout_keeps_indentation():
    result = words_from(["select a,", "b", "from t"], indent=[0, 7, 0])
    assert layout_text(result) == "select a,\n       b\nfrom t"


def test_json_repair_only_outside_strings():
    text, found = fixes.fix_json("{'pedido': 15147800, msg: 'erro, codigo: 5', “itens”: [{'cod': 1,}], ok: True}")
    reading = document.read(text)
    assert reading.ok and reading.value == {"pedido": 15147800, "msg": "erro, codigo: 5", "itens": [{"cod": 1}], "ok": True}
    assert ("True", "true") in [(f.before, f.after) for f in found]
    assert document.read('{"a": 1 "b": 2}').error == "linha 1, coluna 9: falta uma vírgula"


def test_json_paths_records_and_description():
    value = {"pedido": 1, "itens": [{"cod": 1, "nome": "a"}, {"cod": 2, "obs": None}]}
    assert document.path(["itens", 0, "cod"]) == "itens[0].cod" and document.path(["a b"]) == '["a b"]'
    parts, objects = document.records(value)
    assert parts == ["itens"] and document.to_rows(objects) == [["cod", "nome", "obs"], ["1", "a", ""], ["2", "", ""]]
    reading = document.read(document.compact(value))
    assert document.describe(reading) == "Objeto com 2 chaves: 3 níveis; a lista itens tem 2 objetos com cod, nome, obs; " \
                                         "1 campo nulo."


def test_grid_columns_from_alignment_with_empty_cell():
    cells = [["Código do produto", "Descrição", "Preço", "Estoque"], ["1", "Arroz", "1.240,50", "10"],
             ["2", "", "7", "1O"], ["3", "Café", "18,90", "4"], ["4", "Feijão preto", "9,99", "12"]]
    rows = grid.table_rows(grid_words(cells, [10, 170, 330, 450]))
    assert rows == cells  # a célula vazia não puxa o 7 para a coluna Descrição
    assert grid.has_header(rows) and grid.suspicious(rows, True) == {(2, 3): "10"}
    stats = grid.column_stats(rows)
    assert grid.describe(rows, True, stats) == "4 linhas e 4 colunas: preco soma 1.276,39."  # não soma o código
    assert grid.to_markdown(rows[:2]).splitlines()[1] == "| --- | --- | --- | --- |"
    assert grid.to_insert(rows[:2], "produtos", comma_decimal=True) == \
        "INSERT INTO produtos (codigo_do_produto, descricao, preco, estoque) VALUES (1, 'Arroz', 1240.50, 10);"
    assert grid.to_update(rows[:2], "produtos", key=0, comma_decimal=True) == \
        "UPDATE produtos SET descricao = 'Arroz', preco = 1240.50, estoque = 10 WHERE codigo_do_produto = 1;"
    assert '"preco": 1240.5' in grid.to_json(rows[:2])


def test_detect_each_kind():
    assert detect(words_from(["select c.codcli FR0M clientes c", "where c.uf = 'SP'"])) is Kind.SQL
    assert detect(words_from(['{"pedido": 1,', '"itens": [1, 2]}'])) is Kind.JSON
    table = grid_words([["Cod", "Nome"], ["1", "Ana"], ["2", "Bia"]], [10, 200])
    assert detect(OcrResult(tuple(table), "x")) is Kind.TABLE
    assert detect(words_from(["Bom dia, tudo certo?"])) is Kind.TEXT
    assert detect(OcrResult()) is None


def test_reading_score_prefers_clean_text():
    assert reading_score("join pedidos p on p.codcli = c.codcli") > reading_score(".o--.   d d =  o  opp .")


def test_schema_learns_and_builds_templates(tmp_path):
    schema = Schema(tmp_path / "estrutura.json")
    schema.learn_query("select c.codcli, c.nome from clientes c left join pedidos p on p.codcli = c.codcli "
                       "where c.uf = 'SP' and p.valor > 10")
    schema.learn_query("update produtos set preco = 1, estoque = 2 where codprod = 5")
    assert schema.tables == {"clientes": ["codcli", "nome", "uf"], "pedidos": ["codcli", "valor"],
                             "produtos": ["preco", "estoque", "codprod"]}
    assert Schema(tmp_path / "estrutura.json").tables == schema.tables  # ficou guardado
    assert schema.search("cl") == ["clientes"] and schema.search("o")[:2] == ["pedidos", "produtos"]
    assert schema.template("clientes", "select") == ("SELECT c.codcli,\n       c.nome,\n       c.uf\n"
                                                     "FROM clientes c\nWHERE ")
    assert schema.template("clientes", "insert") == ("INSERT INTO clientes (codcli, nome, uf)\n"
                                                     "VALUES (/* codcli */, /* nome */, /* uf */);")
    assert schema.template("produtos", "update") == ("UPDATE produtos\n   SET preco = /* preco */,\n"
                                                     "       estoque = /* estoque */\n WHERE codprod = /* codprod */;")
    schema.forget("pedidos")
    assert "pedidos" not in Schema(tmp_path / "estrutura.json").tables


def test_grid_with_apostrophe_and_missing_value():
    cells = [["id", "nome", "valor"], ["1", "Ana Paula", "10.5"], ["2", "O'Neil", ""], ["3", "Bruno", "7"]]
    rows = grid.table_rows(grid_words(cells, [10, 170, 330]))
    assert rows == cells and grid.looks_like_table(rows)
    assert grid.to_tsv(rows).splitlines()[1] == "1\tAna Paula\t10.5"
    assert grid.to_csv(rows).splitlines()[0] == "id;nome;valor"
    assert grid.to_insert(rows).splitlines()[1] == "INSERT INTO tabela (id, nome, valor) VALUES (2, 'O''Neil', NULL);"


def test_plain_text_is_not_a_table():
    words = [Word(w, QRectF(10 + i * 50, 10 + line * 22, 44, 16), line)
             for line in range(3) for i, w in enumerate("um texto corrido normal".split())]
    assert not grid.looks_like_table(grid.table_rows(words))


def test_column_stats_with_brazilian_numbers():
    rows = [["Cod", "Preço", "Cliente"], ["1", "1.240,50", "Ana"], ["2", "R$ 7", ""], ["3", "", "Ana"]]
    cod, price, client = grid.column_stats(rows)
    assert (cod.kind, cod.sum) == ("número", 6) and grid.key_like(cod, first=True)
    assert (price.kind, price.filled, price.sum, price.max) == ("número", 2, 1247.5, 1240.5)
    assert (client.kind, client.filled, client.distinct) == ("texto", 2, 1)
    assert grid.brl(1247.5) == "1.247,50" and grid.brl(6.0) == "6"
