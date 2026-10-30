"""Configurações, abertas pela galeria ou pela bandeja.

Cada mudança vale na hora (não tem botão de salvar); a próxima captura já usa.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from klick import __author__, __version__, audio, config, ocr, theme
from klick.hotkeys import KeyRecorder
from klick.icon import app_icon
from klick.recorder import QUALITIES
from klick.recording_ui import FORMATS, SOUND_OPTIONS
from klick.widgets import Segmented, Switch, button

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

HOTKEY_TEXT = {
    "capture": "Seleciona uma área para copiar, salvar, editar, ler ou analisar. Só imagem.",
    "record": "Seleciona uma área e grava vídeo ou GIF. Aperte de novo para parar.",
    "ocr": "Seleciona e já copia o texto, sem abrir janela.",
}
SAVE_ROWS = [
    ("prints", "Prints", "Quando você copia um print."),
    ("reading", "Leituras e análises", "O texto lido (Ler e Análise) vira um .txt."),
    ("recordings", "Gravações", "O vídeo MP4."),
    ("gifs", "GIFs", "O arquivo GIF."),
]
SAVE_OPTIONS = [("folder", "Na pasta"), ("gallery", "Só na galeria")]
TEMP_OPTIONS = [("1", "1 dia"), ("7", "7 dias"), ("30", "30 dias"), ("0", "Nunca")]

# (seção, [(opção, título, descrição)])
SWITCHES = [
    ("Captura", [
        ("loupe", "Lupa de pixels", "Mostra os pixels ampliados, a posição e a cor embaixo do mouse ao selecionar."),
        ("guides", "Linhas de terço", "Divide a seleção em 3 × 3 enquanto você arrasta."),
        ("toasts", "Aviso depois de copiar", "Cartão no canto da tela com Editar, Ler, Pesquisar e Guardar."),
    ]),
    ("Gravação", [
        ("record_ask", "Perguntar antes de gravar",
         "Mostra formato, som e qualidade a cada gravação. Desligado, usa os padrões abaixo."),
    ]),
    ("Leitura e Análise", [
        ("precise_ocr", "Leitura precisa",
         "Depois da leitura do Windows, o RapidOCR lê de novo (1 a 4 s) e corrige. Desligado, fica só a do Windows."),
        ("addon_sql", "Análise de SQL, JSON e tabelas",
         "Mostra o botão Análise na leitura quando o texto é uma consulta, um JSON ou uma grade."),
    ]),
]


def startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, "Klick")
        return True
    except OSError:
        return False


def set_startup(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if not enabled:
            try:
                winreg.DeleteValue(key, "Klick")
            except OSError:
                pass
            return
        if getattr(sys, "frozen", False):
            command = f'"{sys.executable}" --startup'
        else:
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            command = f'"{pythonw if pythonw.exists() else sys.executable}" -m klick --startup'
        winreg.SetValueEx(key, "Klick", 0, winreg.REG_SZ, command)


class ShortcutButton(QPushButton):
    """Mostra o atalho; clicado, espera você apertar a combinação nova (Esc cancela)."""

    listening = Signal(bool)
    changed = Signal(str, str)  # nome, combinação

    def __init__(self, name: str):
        super().__init__(config.hotkey_label(config.hotkeys()[name]))
        self.name = name
        self.setProperty("variant", "secondary")
        self.setFont(theme.font(12.5, 600, mono=True))
        self.setMinimumWidth(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clique e aperte a combinação nova. Funciona com teclas do FN do notebook.")
        self._recorder = KeyRecorder(self)
        self._recorder.recorded.connect(self._on_recorded)
        self.clicked.connect(self.listen)

    def listen(self) -> None:
        self.listening.emit(True)
        if not self._recorder.start():
            self.listening.emit(False)
            return
        self.setText("Aperte as teclas…")

    def show_combo(self, combo: str) -> None:
        self.setText(config.hotkey_label(combo))

    def _on_recorded(self, combo: str) -> None:
        self._recorder.stop()
        self.show_combo(combo or config.hotkeys()[self.name])
        if combo:
            self.changed.emit(self.name, combo)
        self.listening.emit(False)


class SettingsDialog(QDialog):
    historyToggled = Signal(bool)
    hotkeysPaused = Signal(bool)  # um atalho novo está sendo gravado: os atuais não devem disparar
    hotkeysChanged = Signal()
    savingChanged = Signal()

    def __init__(self, parent: QWidget | None = None, section: str = ""):
        super().__init__(parent, Qt.WindowType.Dialog)
        scheme = theme.window_scheme()
        self.setObjectName("window")
        self.setWindowTitle("Klick: configurações")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(theme.window_stylesheet(scheme) + f"""
            QFrame#group {{ background: {scheme.surface}; border: 1px solid {scheme.line};
                border-radius: {theme.WINDOW_RADIUS}px; }}
            QFrame#rule {{ background: {scheme.line}; }}""")
        self.resize(640, 760)
        self.switches: dict[str, Switch] = {}
        self.shortcuts: dict[str, ShortcutButton] = {}
        self.saving: dict[str, Segmented] = {}
        self._anchors: dict[str, QWidget] = {}

        content = QWidget()
        content.setObjectName("window")
        col = QVBoxLayout(content)
        col.setContentsMargins(22, 18, 22, 22)
        col.setSpacing(10)

        heading = QLabel("Configurações")
        heading.setFont(theme.font(24, 800))
        col.addWidget(heading)

        group = self._group("Atalhos", col, "hotkeys")
        for name, label in config.HOTKEY_NAMES.items():
            shortcut = ShortcutButton(name)
            shortcut.listening.connect(self.hotkeysPaused.emit)
            shortcut.changed.connect(self._set_hotkey)
            self.shortcuts[name] = shortcut
            self._row(group, label, HOTKEY_TEXT[name], shortcut)
        self._hotkey_note = QLabel("")
        self._hotkey_note.setProperty("role", "muted")
        self._hotkey_note.setWordWrap(True)
        reset = button("Voltar aos atalhos padrão", "ghost", "undo")
        reset.clicked.connect(self._reset_hotkeys)
        line = QHBoxLayout()
        line.addWidget(self._hotkey_note, 1)
        line.addWidget(reset)
        group.addLayout(line)

        group = self._group("Onde salvar", col, "saving")
        for kind, label, text in SAVE_ROWS:
            choice = Segmented(SAVE_OPTIONS, config.save_policy(kind))
            choice.changed.connect(lambda value, k=kind: self._set_policy(k, value))
            self.saving[kind] = choice
            self._row(group, label, text, choice)
        self.temp_days = Segmented(TEMP_OPTIONS, str(config.temp_days()))
        self.temp_days.changed.connect(self._set_temp_days)
        self._row(group, "Apagar o que está só na galeria depois de",
                  "Conta a partir da captura. Guardar na pasta (Ctrl+S na galeria) tira do prazo.", self.temp_days,
                  below=True)
        self._folder = QLabel(str(config.save_dir()))
        self._folder.setProperty("role", "muted")
        self._folder.setWordWrap(True)
        self._folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        change = button("Alterar…", "secondary")
        change.clicked.connect(self._choose_folder)
        open_ = button("Abrir", "ghost", "folder")
        open_.clicked.connect(lambda: self._open(config.save_dir()))
        self._rule(group)
        title = QLabel("Pasta do Klick")
        title.setFont(theme.font(13.5, 700))
        group.addWidget(title)
        line = QHBoxLayout()
        line.addWidget(self._folder, 1)
        line.addWidget(open_)
        line.addWidget(change)
        group.addLayout(line)
        sub = QLabel("Dentro dela: " + " · ".join(f"{name}/" for name in config.FOLDERS.values()))
        sub.setProperty("role", "muted")
        sub.setFont(theme.font(11.5, 500, mono=True))
        group.addWidget(sub)

        for section, rows in SWITCHES:
            group = self._group(section, col)
            for name, title_, text in rows:
                sw = Switch(config.option(name))
                sw.setAccessibleName(title_)
                sw.toggled.connect(lambda on, n=name: config.set_option(n, on))
                self.switches[name] = sw
                if name == "precise_ocr" and not ocr.precise_available():
                    sw.setEnabled(False)
                    text += " (motor não instalado)"
                self._row(group, title_, text, sw)
            if section == "Gravação":
                self._recording_defaults(group)

        group = self._group("Sistema", col)
        keep = Switch(config.history_enabled())
        keep.toggled.connect(config.set_history_enabled)
        keep.toggled.connect(self.historyToggled.emit)
        self.switches["history"] = keep
        self._row(group, "Guardar histórico",
                  "Cada captura entra na galeria e fica pesquisável pelo texto. Desligado, nada é guardado.", keep)
        if sys.platform == "win32":
            start = Switch(startup_enabled())
            start.toggled.connect(set_startup)
            self.switches["startup"] = start
            self._row(group, "Abrir com o Windows", "O Klick já começa na bandeja quando você liga o computador.", start)

        about = QLabel(f"Klick {__version__} · criado por {__author__}")
        about.setProperty("role", "muted")
        about.setFont(theme.font(11.5, 500))
        about.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addSpacing(8)
        col.addWidget(about)
        col.addStretch(1)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        foot = QHBoxLayout()
        foot.setContentsMargins(22, 10, 22, 14)
        note = QLabel("As mudanças valem na hora.")
        note.setProperty("role", "muted")
        close = button("Fechar", "primary")
        close.clicked.connect(self.accept)
        foot.addWidget(note)
        foot.addStretch(1)
        foot.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll, 1)
        layout.addLayout(foot)
        QShortcut(QKeySequence("Escape"), self, activated=self.accept)
        if section in self._anchors:
            QTimer.singleShot(0, lambda: scroll.ensureWidgetVisible(self._anchors[section], 0, 0))

    # --- montagem ----------------------------------------------------------

    def _group(self, title: str, col: QVBoxLayout, anchor: str = "") -> QVBoxLayout:
        label = QLabel(title.upper())
        label.setProperty("role", "section")
        label.setFont(theme.font(11, 800, caps=True))
        col.addSpacing(8)
        col.addWidget(label)
        frame = QFrame(objectName="group")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(10)
        col.addWidget(frame)
        if anchor:
            self._anchors[anchor] = label
        return inner

    @staticmethod
    def _rule(group: QVBoxLayout) -> None:
        if group.count():
            rule = QFrame(objectName="rule")
            rule.setFixedHeight(1)
            group.addWidget(rule)

    def _row(self, group: QVBoxLayout, title: str, text: str, control: QWidget, below: bool = False) -> None:
        self._rule(group)
        words = QVBoxLayout()
        words.setSpacing(2)
        head = QLabel(title)
        head.setFont(theme.font(13.5, 700))
        body = QLabel(text)
        body.setProperty("role", "muted")
        body.setWordWrap(True)
        body.setFont(theme.font(12, 500))
        words.addWidget(head)
        words.addWidget(body)
        if below:  # controle largo (Segmented): fica embaixo do texto
            words.addSpacing(4)
            words.addWidget(control, 0, Qt.AlignmentFlag.AlignLeft)
            group.addLayout(words)
            return
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addLayout(words, 1)
        row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        group.addLayout(row)

    def _recording_defaults(self, group: QVBoxLayout) -> None:
        fmt = Segmented(FORMATS, config.record_format())
        fmt.changed.connect(config.set_record_format)
        sound = Segmented(SOUND_OPTIONS, config.record_audio())
        sound.changed.connect(config.set_record_audio)
        quality = Segmented([(k, q.label) for k, q in QUALITIES.items()], config.record_quality())
        quality.changed.connect(config.set_record_quality)
        self.format, self.sound, self.quality = fmt, sound, quality
        self._row(group, "Formato padrão", "O que já vem escolhido quando você aperta o atalho de gravar.", fmt,
                  below=True)
        text = "Computador e microfone." if audio.available() else "Só o microfone (o som do computador não está disponível)."
        self._row(group, "Som padrão", text, sound, below=True)
        self._row(group, "Qualidade padrão", "Baixa 15 fps · Média 30 fps · Alta 60 fps.", quality, below=True)

    # --- ações -------------------------------------------------------------

    def _set_hotkey(self, name: str, combo: str) -> None:
        taken = next((config.HOTKEY_NAMES[n] for n, c in config.hotkeys().items() if c == combo and n != name), None)
        if taken:
            self.shortcuts[name].show_combo(config.hotkeys()[name])
            self._hotkey_note.setText(f"{config.hotkey_label(combo)} já é o atalho de “{taken}”.")
            return
        config.set_hotkey(name, combo)
        self._hotkey_note.setText(f"{config.HOTKEY_NAMES[name]}: {config.hotkey_label(combo)}.")
        self.hotkeysChanged.emit()

    def _reset_hotkeys(self) -> None:
        for name, combo in config.DEFAULT_HOTKEYS.items():
            config.set_hotkey(name, combo)
            self.shortcuts[name].show_combo(combo)
        self._hotkey_note.setText("Atalhos padrão de volta.")
        self.hotkeysChanged.emit()

    def _set_policy(self, kind: str, value: str) -> None:
        config.set_save_policy(kind, value)
        self.savingChanged.emit()

    def _set_temp_days(self, value: str) -> None:
        config.set_temp_days(int(value))
        self.savingChanged.emit()

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Pasta do Klick", str(config.save_dir()))
        if path:
            config.set_save_dir(Path(path))
            self._folder.setText(path)

    @staticmethod
    def _open(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
