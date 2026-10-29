"""Configurações, abertas pela galeria: o usuário liga e desliga o que quiser.

Cada mudança vale na hora (não tem botão de salvar); a próxima captura já usa.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

from klick import audio, config, ocr, theme
from klick.icon import app_icon
from klick.recorder import QUALITIES
from klick.recording_ui import SOUND_OPTIONS
from klick.widgets import Segmented, Switch, button

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# (seção, [(opção, título, descrição)])
SWITCHES = [
    ("Captura", [
        ("loupe", "Lupa de pixels", "A lupa com coordenadas e cor que segue o mouse ao selecionar."),
        ("guides", "Guias de terço", "Linhas que dividem a seleção em três enquanto você arrasta."),
        ("toasts", "Aviso depois de copiar", "O cartão no canto da tela com Marcar, Ler e Salvar."),
        ("autosave", "Salvar todo print na pasta", "Além de copiar, grava cada print em Prints."),
    ]),
    ("Leitura", [
        ("precise_ocr", "Leitura precisa", "O RapidOCR refina o texto 1 a 4 s depois. Desligado, fica só o do Windows."),
    ]),
    ("Gravação", [
        ("record_ask", "Perguntar antes de gravar", "Mostra som e qualidade a cada gravação. Desligado, usa o padrão abaixo."),
    ]),
    ("Extras", [
        ("addon_sql", "SQL e tabelas", "Na leitura: conserta e formata consultas SQL, e transforma grades de resultado "
                                       "em texto para o Excel, CSV ou INSERT."),
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


class SettingsDialog(QDialog):
    historyToggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Dialog)
        scheme = theme.window_scheme()
        self._scheme = scheme
        self.setObjectName("window")
        self.setWindowTitle("Klick: configurações")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(theme.window_stylesheet(scheme) + f"""
            QFrame#group {{ background: {scheme.surface}; border: 1px solid {scheme.line}; border-radius: 4px; }}
            QFrame#rule {{ background: {scheme.line}; }}""")
        self.resize(560, 720)
        self.switches: dict[str, Switch] = {}

        content = QWidget()
        content.setObjectName("window")
        col = QVBoxLayout(content)
        col.setContentsMargins(20, 16, 20, 20)
        col.setSpacing(10)

        heading = QLabel("Configurações")
        heading.setFont(theme.font(22, 800, 125))
        col.addWidget(heading)

        for section, rows in SWITCHES:
            group = self._group(section, col)
            for name, title, text in rows:
                sw = Switch(config.option(name))
                sw.setAccessibleName(title)
                sw.toggled.connect(lambda on, n=name: config.set_option(n, on))
                self.switches[name] = sw
                if name == "precise_ocr" and not ocr.precise_available():
                    sw.setEnabled(False)
                    text += " (motor não instalado)"
                self._row(group, title, text, sw)
            if section == "Gravação":
                self._recording_defaults(group)

        group = self._group("Pastas", col)
        self._folder = QLabel(str(config.save_dir()))
        self._folder.setProperty("role", "muted")
        self._folder.setWordWrap(True)
        self._folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        change = button("Alterar…", "secondary")
        change.clicked.connect(self._choose_folder)
        open_ = button("Abrir", "ghost", "folder")
        open_.clicked.connect(lambda: self._open(config.save_dir()))
        line = QHBoxLayout()
        line.addWidget(self._folder, 1)
        line.addWidget(open_)
        line.addWidget(change)
        group.addLayout(line)
        sub = QLabel("Dentro dela: " + " · ".join(f"{name}/" for name in config.FOLDERS.values()))
        sub.setProperty("role", "muted")
        sub.setFont(theme.font(11.5, 400, mono=True))
        group.addWidget(sub)

        group = self._group("Sistema", col)
        keep = Switch(config.history_enabled())
        keep.toggled.connect(config.set_history_enabled)
        keep.toggled.connect(self.historyToggled.emit)
        self.switches["history"] = keep
        self._row(group, "Guardar histórico", "As capturas aparecem aqui na galeria e ficam pesquisáveis.", keep)
        if sys.platform == "win32":
            start = Switch(startup_enabled())
            start.toggled.connect(set_startup)
            self.switches["startup"] = start
            self._row(group, "Abrir com o Windows", "O Klick já fica na bandeja quando você liga o computador.", start)
        col.addStretch(1)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        foot = QHBoxLayout()
        foot.setContentsMargins(20, 10, 20, 14)
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

    # --- montagem ----------------------------------------------------------

    def _group(self, title: str, col: QVBoxLayout) -> QVBoxLayout:
        label = QLabel(title.upper())
        label.setProperty("role", "muted")
        label.setFont(theme.font(11, 600, mono=True))
        col.addSpacing(6)
        col.addWidget(label)
        frame = QFrame(objectName="group")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(14, 10, 14, 10)
        inner.setSpacing(10)
        col.addWidget(frame)
        return inner

    def _row(self, group: QVBoxLayout, title: str, text: str, control: QWidget, below: bool = False) -> None:
        if group.count():
            rule = QFrame(objectName="rule")
            rule.setFixedHeight(1)
            group.addWidget(rule)
        words = QVBoxLayout()
        words.setSpacing(2)
        head = QLabel(title)
        head.setFont(theme.font(13.5, 600))
        body = QLabel(text)
        body.setProperty("role", "muted")
        body.setWordWrap(True)
        body.setFont(theme.font(12, 400))
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
        sound = Segmented(SOUND_OPTIONS, config.record_audio())
        sound.changed.connect(config.set_record_audio)
        quality = Segmented([(k, q.label) for k, q in QUALITIES.items()], config.record_quality())
        quality.changed.connect(config.set_record_quality)
        self.sound, self.quality = sound, quality
        text = "Som do computador e microfone." if audio.available() else "Só o microfone (som do computador indisponível)."
        self._row(group, "Som padrão", text, sound, below=True)
        self._row(group, "Qualidade padrão", "Baixa 15 fps · Média 30 fps · Alta 60 fps.", quality, below=True)

    # --- ações -------------------------------------------------------------

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Pasta do Klick", str(config.save_dir()))
        if path:
            config.set_save_dir(Path(path))
            self._folder.setText(path)

    @staticmethod
    def _open(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
