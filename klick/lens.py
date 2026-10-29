"""Pesquisa a imagem no Google Lens pelo navegador padrão.

O Lens não aceita imagem pela URL, então o Klick gera uma página local que já traz
a imagem e envia o formulário de upload do Lens assim que abre (o mesmo envio que
a página do Lens faz ao arrastar uma imagem). Não é API oficial: se o Google mudar,
a página mostra um link para abrir o Lens e colar a imagem, que fica no clipboard.
"""

from __future__ import annotations

import base64
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt, QUrl, QUrlQuery
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage

UPLOAD = "https://lens.google.com/v3/upload"
MAX_SIDE = 2000  # o Lens reduz de qualquer jeito; menor sobe mais rápido

PAGE = """<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><title>Klick: pesquisando no Google Lens…</title>
<body style="font-family:Segoe UI,sans-serif;background:#121110;color:#efede8;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center">
<p style="font-size:18px">Enviando a imagem para o Google Lens…</p>
<p style="color:#a8a398;font-size:14px">Se nada acontecer, <a style="color:#ff8a47" href="https://lens.google.com/">abra o Lens</a> e cole (Ctrl+V): a imagem já está copiada.</p>
</div>
<form id="f" method="post" enctype="multipart/form-data" action="{action}">
<input type="file" name="encoded_image" id="i" hidden></form>
<script>
const bytes = Uint8Array.from(atob("{data}"), c => c.charCodeAt(0));
const file = new File([bytes], "klick.jpg", {{type: "image/jpeg"}});
const dt = new DataTransfer(); dt.items.add(file);
document.getElementById("i").files = dt.files;
document.getElementById("f").submit();
</script></body></html>
"""


def jpeg_base64(image: QImage) -> str:
    if max(image.width(), image.height()) > MAX_SIDE:
        image = image.scaled(MAX_SIDE, MAX_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG", 90)
    return base64.b64encode(bytes(buffer.data())).decode("ascii")


def page(image: QImage) -> str:
    action = f"{UPLOAD}?ep=ccm&s=&st={int(time.time() * 1000)}"
    return PAGE.format(action=action, data=jpeg_base64(image))


def search_image(image: QImage) -> Path:
    """Abre o navegador já pesquisando `image`. Devolve a página gerada."""
    QGuiApplication.clipboard().setImage(image)  # plano B: colar no Lens
    folder = Path(tempfile.gettempdir()) / "klick"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("lens_*.html"):  # páginas de pesquisas anteriores
        old.unlink(missing_ok=True)
    target = folder / f"lens_{int(time.time())}.html"
    target.write_text(page(image), encoding="utf-8")
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
    return target


def search_text(text: str) -> None:
    """Pesquisa o trecho no Google (usado na leitura)."""
    url = QUrl("https://www.google.com/search")
    query = QUrlQuery()
    query.addQueryItem("q", " ".join(text.split())[:500])
    url.setQuery(query)
    QDesktopServices.openUrl(url)
