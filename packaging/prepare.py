"""Gera em build/ o que o PyInstaller precisa: klick.ico e version.txt (propriedades do .exe)."""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from klick import __version__  # noqa: E402
from klick.icon import _draw  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)

VERSION_INFO = """\
VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple}, prodvers={tuple}),
  kids=[
    StringFileInfo([StringTable("041604B0", [
      StringStruct("CompanyName", "Lucas Nagib"),
      StringStruct("LegalCopyright", "Criado por Lucas Nagib"),
      StringStruct("FileDescription", "Klick - captura de tela"),
      StringStruct("FileVersion", "{version}"),
      StringStruct("InternalName", "Klick"),
      StringStruct("OriginalFilename", "Klick.exe"),
      StringStruct("ProductName", "Klick"),
      StringStruct("ProductVersion", "{version}"),
    ])]),
    VarFileInfo([VarStruct("Translation", [0x0416, 1200])]),
  ],
)
"""


def png_bytes(size: int) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    _draw(size).save(buffer, "PNG")
    return bytes(buffer.data())


def write_ico(path: Path) -> None:
    # ICO com as imagens em PNG (aceito desde o Vista): cabeçalho, diretório e os dados.
    images = [png_bytes(size) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    for size, data in zip(SIZES, images):
        side = 0 if size >= 256 else size  # 0 significa 256 no formato ICO
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + entries + b"".join(images))


def write_version(path: Path) -> None:
    parts = tuple(int(p) for p in __version__.split(".")) + (0,) * (4 - len(__version__.split(".")))
    path.write_text(VERSION_INFO.format(tuple=parts, version=__version__), encoding="utf-8")


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication(sys.argv[:1])
    write_ico(out / "klick.ico")
    write_version(out / "version.txt")
    print(__version__)
