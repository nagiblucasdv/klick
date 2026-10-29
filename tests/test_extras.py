from pathlib import Path

from PySide6.QtGui import QColor, QImage

from klick import lens, sql
from klick.recorder import QUALITIES, encoder_args, gif_args, mux_args, record_args
from PySide6.QtCore import QRect


def test_quality_changes_encoder_and_gif():
    assert encoder_args("libx264", QUALITIES["high"])[-1] == "18"
    assert encoder_args("libopenh264", QUALITIES["low"])[-1] == "2M"
    vf = gif_args(Path("a.mp4"), Path("a.gif"), QUALITIES["low"])
    assert "fps=8," in vf[vf.index("-vf") + 1] and "640" in vf[vf.index("-vf") + 1]


def test_microphone_goes_into_ffmpeg():
    args = record_args(QRect(0, 0, 100, 100), Path("o.mp4"), 30, platform="win32", mic="Microfone (X)")
    assert args[args.index("dshow") + 4] == "audio=Microfone (X)"
    assert "aac" in args and args[-1] == "o.mp4"


def test_mux_mixes_system_sound_with_microphone():
    alone = mux_args(Path("v.mp4"), [Path("s.wav")], Path("o.mp4"), video_has_audio=False)
    assert "-filter_complex" not in alone and alone[alone.index("-map") + 3] == "1:a"
    both = mux_args(Path("v.mp4"), [Path("s.wav")], Path("o.mp4"), video_has_audio=True)
    assert "[0:a][1:a]amix=inputs=2" in both[both.index("-filter_complex") + 1]
    assert both[-1] == "o.mp4" and "copy" in both


def test_sql_detection_and_tidy():
    text = "select id, nome FR0M clientes c\nJOIN pedidos p on p.cliente = c.id where p.valor > 10"
    assert sql.looks_like_sql(text)
    assert not sql.looks_like_sql("Selecione a área e depois clique em salvar")
    out = sql.tidy(text)
    assert out.startswith("SELECT") and "\nFROM clientes" in out
    assert sql.tables(out) == ["clientes", "pedidos"]


def test_lens_page_carries_the_image(qapp):
    image = QImage(40, 30, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    page = lens.page(image)
    assert lens.UPLOAD in page and 'name="encoded_image"' in page
    assert lens.jpeg_base64(image) in page


def _grid_words():
    from PySide6.QtCore import QRectF

    from klick.ocr import Word

    cells = [["id", "nome", "valor"], ["1", "Ana Paula", "10.5"], ["2", "O'Neil", ""], ["3", "Bruno", "7"]]
    words = []
    for r, row in enumerate(cells):
        for c, text in enumerate(row):
            x = 10 + c * 160
            for part in text.split():
                width = 9 * len(part)
                words.append(Word(part, QRectF(x, 10 + r * 30, width, 16), r * 10 + c))  # linhas do RapidOCR: uma por caixa
                x += width + 5
    return words


def test_grid_from_words():
    rows = sql.table_rows(_grid_words())
    assert rows == [["id", "nome", "valor"], ["1", "Ana Paula", "10.5"], ["2", "O'Neil", ""], ["3", "Bruno", "7"]]
    assert sql.looks_like_table(rows)
    assert sql.to_tsv(rows).splitlines()[1] == "1\tAna Paula\t10.5"
    assert sql.to_csv(rows).splitlines()[0] == "id;nome;valor"
    inserts = sql.to_insert(rows).splitlines()
    assert inserts[1] == "INSERT INTO tabela (id, nome, valor) VALUES (2, 'O''Neil', NULL);"


def test_plain_text_is_not_a_table():
    from PySide6.QtCore import QRectF

    from klick.ocr import Word

    words = [Word(w, QRectF(10 + i * 50, 10 + line * 22, 44, 16), line)
             for line in range(3) for i, w in enumerate("um texto corrido normal".split())]
    assert not sql.looks_like_table(sql.table_rows(words))
