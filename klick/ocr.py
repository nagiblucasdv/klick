"""OCR com o motor nativo do Windows (Windows.Media.Ocr, via pywinrt).

O reconhecimento roda numa thread própria: a thread principal do Qt é STA e o
`.get()` de uma operação assíncrona do WinRT não pode bloquear uma STA.
"""

from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import cache

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QImage

MAX_UPSCALED_AREA = 2_000_000  # acima disso, ampliar só deixa o OCR mais lento


class OcrError(RuntimeError):
    pass


@dataclass(frozen=True)
class Word:
    text: str
    rect: QRectF  # em pixels da imagem original
    line: int


@dataclass(frozen=True)
class OcrResult:
    """Palavras em ordem de leitura, com a posição de cada uma (para selecionar como no Google Lens)."""
    words: tuple[Word, ...] = ()
    language: str = ""
    lines: tuple[str, ...] = field(default=())

    @property
    def text(self) -> str:
        return "\n".join(self.lines) if self.lines else self.text_between(0, len(self.words) - 1)

    def text_between(self, first: int, last: int) -> str:
        """Texto das palavras first..last (inclusive): espaço na mesma linha, quebra entre linhas."""
        if not self.words:
            return ""
        first, last = max(0, min(first, last)), min(len(self.words) - 1, max(first, last))
        out, line = [], None
        for word in self.words[first:last + 1]:
            if line is not None:
                out.append(" " if word.line == line else "\n")
            out.append(word.text)
            line = word.line
        return "".join(out)


def scale_for_ocr(size: QSize, max_dimension: int) -> float:
    """Fator de escala para a imagem: amplia prints pequenos e reduz os grandes demais.

    O motor do Windows erra bastante com texto de tela em tamanho normal;
    ampliar 2x melhora muito o reconhecimento.
    """
    largest = max(size.width(), size.height())
    if largest > max_dimension:
        return max_dimension / largest
    if largest * 2 <= max_dimension and size.width() * size.height() * 4 <= MAX_UPSCALED_AREA:
        return 2.0
    return 1.0


def _init_thread() -> None:
    from winrt.runtime import ApartmentType, init_apartment

    init_apartment(ApartmentType.MULTI_THREADED)


@cache
def _executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="klick-ocr", initializer=_init_thread)


@cache
def _engine(language: str | None):
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    if language:
        lang = Language(language)
        if not OcrEngine.is_language_supported(lang):
            raise OcrError(f"O idioma de OCR '{language}' não está instalado no Windows.")
        return OcrEngine.try_create_from_language(lang)
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrError(
            "Nenhum idioma de OCR instalado. Adicione o português em "
            "Configurações > Hora e idioma > Idioma e região, com o recurso de reconhecimento de texto."
        )
    return engine


def _recognize(image: QImage, language: str | None) -> str:
    return _recognize_words(image, language).text


def _recognize_words(image: QImage, language: str | None) -> OcrResult:
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine

    engine = _engine(language)
    factor = scale_for_ocr(image.size(), OcrEngine.max_image_dimension)
    if factor != 1.0:
        image = image.scaled(image.size() * factor, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    # ARGB32 em little-endian fica BGRA na memória, que é o BGRA8 do WinRT.
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        bytes(image.constBits()), BitmapPixelFormat.BGRA8, image.width(), image.height()
    )
    result = engine.recognize_async(bitmap).get()
    words, lines = [], []
    for index, line in enumerate(result.lines):
        lines.append(line.text)
        for word in line.words:
            r = word.bounding_rect
            words.append(Word(word.text, QRectF(r.x / factor, r.y / factor, r.width / factor, r.height / factor),
                              index))
    return OcrResult(tuple(words), engine.recognizer_language.language_tag, tuple(lines))


def recognize(image: QImage, language: str | None = None) -> Future[str]:
    """Extrai o texto da imagem em segundo plano. Erros chegam como OcrError no Future."""
    return _submit(_recognize, image, language)


def recognize_words(image: QImage, language: str | None = None) -> Future[OcrResult]:
    """Como recognize, mas com cada palavra e a posição dela na imagem."""
    return _submit(_recognize_words, image, language)


def _submit(func, image: QImage, language: str | None) -> Future:
    if sys.platform != "win32":
        future: Future[str] = Future()
        future.set_exception(OcrError("Por enquanto o OCR só funciona no Windows."))
        return future
    try:
        import winrt.windows.media.ocr  # noqa: F401
    except ImportError:
        future = Future()
        future.set_exception(OcrError("Pacotes do OCR ausentes. Rode: pip install -e ."))
        return future
    # copy(): a QImage não pode ser compartilhada com a thread enquanto o Qt a usa.
    return _executor().submit(func, image.copy(), language)


# --- leitura precisa (RapidOCR) ----------------------------------------------
#
# Modelos do PaddleOCR rodando no onnxruntime, offline. Bem mais preciso que o motor do
# Windows em texto colorido ou sobre fundo carregado (prints de jogo, telas com imagem),
# mas leva de 1 a 4 s. Por isso a leitura mostra primeiro o resultado do Windows e troca
# por este quando ele chega.

def precise_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        import rapidocr  # noqa: F401
    except ImportError:
        return False
    return True


@cache
def _precise_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="klick-ocr-precise")


@cache
def _rapid():
    from rapidocr import RapidOCR

    return RapidOCR(params={"Global.log_level": "warning"})


PRECISE_PAD = 32  # a seleção corta o texto rente à borda, onde o detector erra; uma margem resolve


def _with_margin(image: QImage, margin: int) -> QImage:
    from PySide6.QtGui import QPainter

    out = QImage(image.width() + 2 * margin, image.height() + 2 * margin, QImage.Format.Format_RGB32)
    out.fill(image.pixelColor(0, 0))  # a cor do canto costuma ser a do fundo
    p = QPainter(out)
    p.drawImage(margin, margin, image)
    p.end()
    return out


PRECISE_UPSCALE_MAX = 2400  # modo código: prints até essa largura/altura (já dobrada) são lidos ampliados 2x
DARK_LUMA = 110  # modo código: fundo mais escuro que isso (editor em tema escuro) é invertido antes de ler


def _bgr_array(image: QImage):
    import numpy as np

    rgb = image.convertToFormat(QImage.Format.Format_BGR888)  # o RapidOCR espera BGR
    array = np.frombuffer(rgb.constBits(), np.uint8).reshape(rgb.height(), rgb.bytesPerLine())
    return array[:, :rgb.width() * 3].reshape(rgb.height(), rgb.width(), 3).copy()


def _recognize_precise(image: QImage, code: bool = False) -> OcrResult:
    # Modo código (janela de SQL): o RapidOCR erra linhas longas de texto claro sobre fundo
    # escuro em fonte pequena, como num editor. Ampliado 2x e com as cores invertidas ele lê
    # certo; as posições voltam à escala original. Em texto comum (páginas, jogos) ampliar
    # junta palavras, então a leitura normal não usa.
    scale = 2 if code and max(image.width(), image.height()) * 2 <= PRECISE_UPSCALE_MAX else 1
    if scale > 1:
        image = image.scaled(image.width() * scale, image.height() * scale, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    pad = PRECISE_PAD * scale
    array = _bgr_array(_with_margin(image, pad))
    if code and array.mean() < DARK_LUMA:
        array = 255 - array
    out = _rapid()(array, return_word_box=True)
    if not out.txts:
        return OcrResult(language="RapidOCR")
    words = []
    for index, line in enumerate(out.word_results or ()):
        for text, _score, box in line:
            xs, ys = [pt[0] for pt in box], [pt[1] for pt in box]
            words.append(Word(text, QRectF((min(xs) - pad) / scale, (min(ys) - pad) / scale,
                                           (max(xs) - min(xs)) / scale, (max(ys) - min(ys)) / scale), index))
    return OcrResult(tuple(words), "RapidOCR", tuple(out.txts))


def recognize_precise(image: QImage, code: bool = False) -> Future[OcrResult]:
    """Leitura precisa com posição das palavras. `code` ajusta para print de código (SQL, editor).

    Sem RapidOCR instalado, o Future falha com OcrError."""
    if not precise_available():
        future: Future[OcrResult] = Future()
        future.set_exception(OcrError("Leitura precisa indisponível (RapidOCR não instalado)."))
        return future
    return _precise_executor().submit(_recognize_precise, image.copy(), code)


def recognize_best(image: QImage, language: str | None = None) -> Future[str]:
    """Texto pelo motor mais preciso disponível (usado pelo OCR direto, Ctrl+Shift+T)."""
    if not precise_available():
        return recognize(image, language)
    outer: Future[str] = Future()

    def done(future: Future) -> None:
        try:
            outer.set_result(future.result().text)
        except Exception:  # noqa: BLE001 - se o preciso falhar, o do Windows ainda serve
            fallback = recognize(image, language)
            fallback.add_done_callback(
                lambda f: outer.set_exception(f.exception()) if f.exception() else outer.set_result(f.result()))

    recognize_precise(image).add_done_callback(done)
    return outer
