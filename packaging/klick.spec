from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# PyInstaller: gera dist/Klick/Klick.exe (pasta, não arquivo único: abre bem mais rápido).
# Rode pelo packaging/build.ps1, que gera o ícone antes.

ROOT = Path(SPECPATH).parent

# O PySide6 traz o Qt inteiro; o Klick só usa Core, Gui, Widgets, Network e Svg (ícones).
QT_EXCLUDES = [
    f"PySide6.{name}" for name in (
        "Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic", "Qt3DRender", "QtBluetooth",
        "QtCharts", "QtConcurrent", "QtDataVisualization", "QtDesigner", "QtGraphs", "QtHelp", "QtHttpServer",
        "QtLocation", "QtMultimedia", "QtMultimediaWidgets", "QtNetworkAuth", "QtNfc", "QtOpenGL",
        "QtOpenGLWidgets", "QtPdf", "QtPdfWidgets", "QtPositioning", "QtQml", "QtQuick", "QtQuick3D",
        "QtQuickControls2", "QtQuickWidgets", "QtRemoteObjects", "QtScxml", "QtSensors", "QtSerialBus",
        "QtSerialPort", "QtSpatialAudio", "QtSql", "QtStateMachine", "QtSvgWidgets", "QtTest",
        "QtTextToSpeech", "QtUiTools", "QtWebChannel", "QtWebEngineCore", "QtWebEngineQuick",
        "QtWebEngineWidgets", "QtWebSockets", "QtWebView", "QtXml",
    )
]

a = Analysis(
    [str(ROOT / "klick" / "__main__.py")],
    pathex=[str(ROOT)],
    # fontes Archivo e JetBrains Mono; modelos e configurações do RapidOCR (baixados pelo build.ps1)
    datas=[(str(ROOT / "klick" / "assets"), "klick/assets"), *collect_data_files("rapidocr")],
    # pynput escolhe o backend em tempo de execução. Os módulos do winrt usados pelo OCR são achados
    # sozinhos; collect_submodules("winrt") estoura a recursão do modulegraph no Python 3.14.
    hiddenimports=["pynput.keyboard._win32", "pynput.mouse._win32",
                   # o RapidOCR escolhe o motor de inferência em tempo de execução; só o onnxruntime vai junto
                   *collect_submodules("rapidocr", filter=lambda name: not any(
                       engine in name for engine in ("torch", "paddle", "openvino", "mnn", "tensorrt")))],
    excludes=["tkinter", "unittest", "pydoc", "torch", "paddle", "openvino", "matplotlib", *QT_EXCLUDES],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Klick",
    console=False,
    icon=str(ROOT / "build" / "klick.ico"),
    version=str(ROOT / "build" / "version.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Klick")
