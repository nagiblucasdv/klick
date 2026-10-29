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
