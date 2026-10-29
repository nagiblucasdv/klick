"""Ponto de entrada: ícone na bandeja, atalho global e sessão de captura."""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import Future
from pathlib import Path

import shiboken6
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCursor, QDesktopServices, QGuiApplication, QImage, QKeySequence
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QSystemTrayIcon, QWidget, QWidgetAction

from klick import __version__, config, icons, lens, ocr, theme
from klick.actions import Action, copy_file, copy_image, copy_text, save_image, store_image
from klick.capture import Selection, grab_screens
from klick.editor import EditorWindow
from klick.history import History
from klick.history_ui import HistoryWindow
from klick.hotkeys import HotkeyListener
from klick.icon import app_icon
from klick.overlay import CaptureSession
from klick.recorder import Recorder, RecordFormat
from klick.reader import ReaderWindow
from klick.recording_ui import SOUND_OPTIONS, RecordingIndicator
from klick.settings_ui import SettingsDialog
from klick.sql_ui import SqlWindow
from klick.single import InstanceServer, send_to_running
from klick.widgets import Toast

log = logging.getLogger("klick")

PREVIEW_CHARS = 60
RECORD_START_DELAY_MS = 120  # deixa o overlay sumir antes do primeiro frame


class KlickApp(QObject):
    # Emitido da thread do OCR; a conexão queued traz o resultado para a thread do Qt.
    _ocrDone = Signal(QImage, str, str)  # imagem, texto, erro

    def __init__(self, app: QApplication, history: History | None = None):
        super().__init__()
        self._app = app
        self._session: CaptureSession | None = None
        self._ocr_pending = False
        self._editors: list[EditorWindow] = []
        self._readers: list[ReaderWindow] = []
        self._recording: tuple[QImage, RecordFormat] | None = None
        self._history = history if history is not None else History()
        self._history_window: HistoryWindow | None = None

        self._recorder = Recorder(self)
        self._recorder.converting.connect(lambda text: self._indicator and self._indicator.set_status(text))
        self._recorder.finished.connect(self._on_record_finished)
        self._recorder.failed.connect(self._on_record_failed)
        self._indicator: RecordingIndicator | None = None

        self._toast: Toast | None = None

        self._tray = QSystemTrayIcon(app_icon(), self)
        self._tray.setToolTip(f"Klick {__version__}")
        menu = QMenu()
        menu.addAction(self._menu_header(menu))
        self._menu_item(menu, "spot", "Capturar área", "Print", lambda: self.start_capture())
        self._menu_item(menu, "read", "Ler texto", "Ctrl+Shift+T", lambda: self.start_capture(Action.OCR))
        self._menu_item(menu, "sql", "Ler SQL ou tabela", None, lambda: self.start_capture(Action.SQL))
        self._record_action = self._menu_item(menu, "rec", "Gravar área", "Ctrl+Shift+R",
                                              lambda: self.toggle_recording(), color=theme.REC)
        menu.addSeparator()
        self._menu_item(menu, "image", "Galeria", None, lambda: self.show_history())
        keep = self._menu_item(menu, "folder", "Guardar histórico", None, None)
        keep.setCheckable(True)
        keep.setChecked(config.history_enabled())
        keep.toggled.connect(config.set_history_enabled)
        # O estilo do menu esconde a marca de seleção; o ícone mostra se está ligado.
        show_state = lambda on: keep.setIcon(  # noqa: E731
            icons.icon("check", theme.S500, size=16) if on else icons.icon("close", theme.G500, size=16))
        keep.toggled.connect(show_state)
        show_state(keep.isChecked())
        self._keep_action = keep
        menu.aboutToShow.connect(lambda: keep.setChecked(config.history_enabled()))
        menu.addSeparator()
        self._menu_item(menu, "power", "Sair", None, lambda: self.quit())
        self._menu = menu  # mantém referência viva
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)

        self._hotkeys = HotkeyListener(config.hotkeys())
        self._hotkeys.triggered.connect(self._on_hotkey)
        self._ocrDone.connect(self._on_ocr_done)

    def run(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.show()
        if self._hotkeys.start():
            log.info("Atalhos globais: %s", config.hotkeys())

    def start_capture(self, direct_action: Action | None = None) -> None:
        if self._session is not None:
            return
        # Pequeno atraso para o menu da bandeja sumir antes de congelar a tela.
        QTimer.singleShot(150, lambda: self._open_session(direct_action))

    def toggle_recording(self) -> None:
        if self._recorder.recording:
            self._recorder.stop()
        elif not self._recorder.busy:
            self.start_capture(Action.RECORD)

    def show_history(self) -> None:
        if self._history_window is None:
            window = HistoryWindow(self._history)
            window.captureRequested.connect(lambda: self.start_capture())
            window.readRequested.connect(lambda image: self._open_reader(image, record=False))
            window.markRequested.connect(lambda image: self._open_editor_image(image))
            window.sqlRequested.connect(lambda image: self._open_sql(image, record=False))
            window.settingsRequested.connect(self.show_settings)
            self._history_window = window
        self._history_window.refresh()
        self._history_window.show()
        self._history_window.raise_()
        self._history_window.activateWindow()

    def show_settings(self) -> None:
        dialog = SettingsDialog(self._history_window)
        dialog.historyToggled.connect(lambda on: self._history_window and self._history_window.refresh())
        dialog.exec()

    @staticmethod
    def _menu_item(menu: QMenu, icon_name: str, text: str, shortcut: str | None, slot,
                   color: str = theme.G300) -> QAction:
        action = QAction(icons.icon(icon_name, color, size=16), text, menu)
        if shortcut:
            # Só para mostrar o atalho global no menu; quem dispara é o HotkeyListener.
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutVisibleInContextMenu(True)
        if slot is not None:
            action.triggered.connect(slot)
        menu.addAction(action)
        return action

    @staticmethod
    def _menu_header(menu: QMenu) -> QWidgetAction:
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(9, 6, 9, 8)
        row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(22, 22))
        name = QLabel("Klick")
        name.setFont(theme.font(14, 750, 120))
        name.setStyleSheet(f"color: {theme.PAPER};")
        version = QLabel(__version__)
        version.setFont(theme.font(11, 400, mono=True))
        version.setStyleSheet(f"color: {theme.G400};")
        row.addWidget(logo)
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(version)
        action = QWidgetAction(menu)
        action.setDefaultWidget(header)
        action.setEnabled(False)
        return action

    def handle_command(self, command: str) -> None:
        """Comando da linha de comando ou repassado por outra instância ("" = só abriu de novo)."""
        if command == "capture":
            self.start_capture()
        elif command == "ocr":
            self.start_capture(Action.OCR)
        elif command == "record":
            self.start_capture(Action.RECORD)
        elif command == "history":
            self.show_history()
        else:
            self.announce()

    def announce(self) -> None:
        """Avisa que o Klick está na bandeja; sem isso, abrir pelo Menu Iniciar parece não fazer nada."""
        key = config.hotkeys()["capture"].replace("<", "").replace(">", "").replace("_", " ").title()
        self._show_toast(Toast("Klick está na bandeja", f"Aperte {key} para capturar", kind="info"))

    def quit(self) -> None:
        if self._recorder.recording:
            self._recorder.stop()
        self._hotkeys.stop()
        self._tray.hide()
        self._app.quit()

    # --- sessão de captura -------------------------------------------------

    def _open_session(self, direct_action: Action | None) -> None:
        if self._session is not None:
            return
        session = CaptureSession(grab_screens(), direct_action)
        session.finished.connect(self._on_finished)
        session.cancelled.connect(self._end_session)
        self._session = session
        session.start()

    def _end_session(self) -> None:
        self._session = None
        self._maybe_quit()

    def _maybe_quit(self) -> None:
        idle = (self._session is None and not self._ocr_pending and self._indicator is None
                and not self._recorder.busy and not self._editors and not self._readers)
        if self._app.property("klick_oneshot") and idle:
            self.quit()

    def _on_finished(self, action: Action, selection: Selection) -> None:
        try:
            if action is Action.OCR:
                self._start_ocr(selection.image)
            elif action is Action.EDIT:
                self._open_editor(selection)
            elif action is Action.READ:
                self._open_reader(selection.image)
            elif action is Action.LENS:
                lens.search_image(selection.image)
            elif action is Action.SQL:
                self._open_sql(selection.image)
            elif action in (Action.RECORD, Action.GIF):
                self._start_recording(selection, RecordFormat.GIF if action is Action.GIF else RecordFormat.MP4)
            else:
                self._deliver(action, selection.image, source="edit" if selection.marked else None)
        finally:
            self._end_session()

    def _deliver(self, action: Action, image: QImage, source: str | None = None) -> None:
        """Copia ou salva a imagem final (direto da seleção ou vinda do editor)."""
        try:
            if action is Action.COPY:
                copy_image(image)
                stored = store_image(image) if config.option("autosave") else None
                where = f"Prints/{stored.name}" if stored else "Prints"
                if config.option("toasts"):
                    self._show_toast(self._capture_toast("Copiado", f"{image.width()} × {image.height()} · {where}",
                                                         image))
            elif action is Action.SAVE:
                path = save_image(image)
                if not path:
                    return
                toast = Toast("Salvo", path.name, image, [("folder", "Mostrar na pasta", "folder")])
                toast.actionTriggered.connect(lambda key: self._reveal(path))
                self._show_toast(toast)
        except OSError as exc:
            self._warn(f"{exc}\nEscolha outra pasta e tente de novo.")
            return
        self._history.add(image, source or action.value)

    # --- editor ------------------------------------------------------------

    def _open_editor(self, selection: Selection) -> None:
        self._open_editor_image(selection.image, selection.device_pixel_ratio)

    def _open_editor_image(self, image: QImage, scale: float = 1.0) -> None:
        editor = EditorWindow(image, scale)
        editor.done.connect(lambda action, image: self._deliver(action, image, source="edit"))
        editor.destroyed.connect(lambda: self._on_editor_closed(editor))
        self._editors.append(editor)
        editor.show()
        editor.raise_()
        editor.activateWindow()

    def _on_editor_closed(self, editor: EditorWindow) -> None:
        if editor in self._editors:
            self._editors.remove(editor)
        self._maybe_quit()

    # --- leitura -----------------------------------------------------------

    def _open_reader(self, image: QImage, record: bool = True) -> ReaderWindow:
        """Abre a leitura estilo Lens. Da captura, o resultado vai para a coleção Leitura."""
        reader = ReaderWindow(image)
        if record:
            reader.recognized.connect(
                lambda result: result.words and self._history.add(image, Action.OCR.value, text=result.text))
        reader.destroyed.connect(lambda: self._on_reader_closed(reader))
        self._readers.append(reader)
        reader.show()
        reader.raise_()
        reader.activateWindow()
        return reader

    def _open_sql(self, image: QImage, record: bool = True) -> SqlWindow:
        """Janela de SQL. Da captura, o que foi lido vai para a coleção Leitura."""
        window = SqlWindow(image)
        if record:
            window.recognized.connect(lambda result: self._history.add(image, Action.OCR.value, text=result.text))
        window.destroyed.connect(lambda: self._on_reader_closed(window))
        self._readers.append(window)
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    def _on_reader_closed(self, reader: ReaderWindow) -> None:
        if reader in self._readers:
            self._readers.remove(reader)
        self._maybe_quit()

    # --- OCR ---------------------------------------------------------------

    def _start_ocr(self, image: QImage) -> None:
        self._ocr_pending = True
        recognize = ocr.recognize_best if config.option("precise_ocr") else ocr.recognize
        recognize(image, config.ocr_language()).add_done_callback(
            lambda future: self._emit_ocr_result(image, future))

    def _emit_ocr_result(self, image: QImage, future: Future[str]) -> None:
        try:
            self._ocrDone.emit(image, future.result(), "")
        except Exception as exc:  # noqa: BLE001 - qualquer falha do WinRT vira aviso
            log.warning("OCR falhou", exc_info=exc)
            self._ocrDone.emit(image, "", str(exc) or type(exc).__name__)

    def _on_ocr_done(self, image: QImage, text: str, error: str) -> None:
        self._ocr_pending = False
        if error:
            self._warn(f"Não foi possível ler o texto: {error}")
        elif not text.strip():
            self._show_toast(Toast("Nenhum texto encontrado", "Tente uma área maior", image, kind="warn"))
        else:
            copy_text(text)
            preview = " ".join(text.split())
            if len(preview) > PREVIEW_CHARS:
                preview = preview[:PREVIEW_CHARS] + "…"
            toast = Toast("Texto copiado", preview, image, [("read", "Abrir na leitura", "read")])
            toast.actionTriggered.connect(lambda key: self._open_reader(image))
            self._show_toast(toast)
            self._history.add(image, Action.OCR.value, text=text)
        self._maybe_quit()

    # --- gravação ----------------------------------------------------------

    def _start_recording(self, selection: Selection, fmt: RecordFormat) -> None:
        sound = dict(SOUND_OPTIONS).get(selection.sound, "") if fmt is RecordFormat.MP4 and selection.sound != "none" else ""
        label = fmt.value.upper() + (f" · {sound.lower()}" if sound else "")
        indicator = RecordingIndicator(selection.logical, self._recorder.elapsed, label)
        indicator.stopRequested.connect(self._recorder.stop)
        self._indicator = indicator
        # O print da área no instante da seleção vira a miniatura na galeria.
        self._recording = (selection.image, fmt)

        def begin() -> None:
            folder = config.folder("gifs" if fmt is RecordFormat.GIF else "recordings")
            self._recorder.start(selection.rect, fmt, folder, selection.quality, selection.sound)
            if self._recorder.recording:
                indicator.show()
                self._record_action.setText("Parar gravação")

        QTimer.singleShot(RECORD_START_DELAY_MS, begin)

    def _close_indicator(self) -> None:
        if self._indicator is not None:
            self._indicator.close()
            self._indicator = None
        self._record_action.setText("Gravar área")

    def _on_record_finished(self, path: str) -> None:
        self._close_indicator()
        copy_file(Path(path))
        kind = "video"
        if self._recording is not None:
            frame, fmt = self._recording
            kind = "gif" if fmt is RecordFormat.GIF else "video"
            self._history.add_media(Path(path), kind, frame, self._recorder.last_duration)
            self._recording = None
        subtitle = f"{Path(path).name} · é só colar"
        if self._recorder.warning:
            subtitle += f"\n{self._recorder.warning}: o vídeo ficou sem esse som"
        toast = Toast("GIF copiado" if kind == "gif" else "Gravação copiada", subtitle, None,
                      [("folder", "Mostrar na pasta", "folder")], kind="warn" if self._recorder.warning else "ok")
        toast.actionTriggered.connect(lambda key: self._reveal(Path(path)))
        self._show_toast(toast)
        self._maybe_quit()

    def _on_record_failed(self, message: str) -> None:
        self._close_indicator()
        self._recording = None
        self._warn(message)
        self._maybe_quit()

    # --- avisos e eventos --------------------------------------------------

    def _show_toast(self, toast: Toast) -> None:
        """Um aviso por vez, no monitor onde está o mouse."""
        log.info("%s", toast.title.text())
        if self._toast is not None and shiboken6.isValid(self._toast):
            self._toast.close()
        self._toast = toast
        toast.show_on(QGuiApplication.screenAt(QCursor.pos()))

    def _capture_toast(self, title: str, subtitle: str, image: QImage) -> Toast:
        toast = Toast(title, subtitle, image, [("mark", "Marcar", "mark"), ("read", "Ler o texto", "read"),
                                               ("lens", "Pesquisar no Google Lens", "lens"), ("save", "Salvar", "save")])
        toast.actionTriggered.connect(lambda key: self._on_toast_action(key, image))
        return toast

    def _on_toast_action(self, key: str, image: QImage) -> None:
        if key == "mark":
            self._open_editor_image(image)
        elif key == "read":
            self._open_reader(image)
        elif key == "lens":
            lens.search_image(image)
        elif key == "save":
            self._deliver(Action.SAVE, image)

    @staticmethod
    def _reveal(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _warn(self, message: str) -> None:
        log.warning(message)
        first, _, rest = message.partition("\n")
        self._show_toast(Toast(first, rest, kind="warn", timeout=7000))

    def _on_hotkey(self, name: str) -> None:
        if name == "capture":
            self.start_capture()
        elif name == "ocr":
            self.start_capture(Action.OCR)
        elif name == "record":
            self.toggle_recording()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.start_capture()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="klick", description="Captura de tela por seleção de área.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--capture", action="store_true", help="abre a seleção imediatamente")
    mode.add_argument("--ocr", action="store_true", help="abre a seleção em modo OCR direto")
    mode.add_argument("--record", action="store_true", help="abre a seleção para gravar a área")
    mode.add_argument("--history", action="store_true", help="abre o histórico")
    parser.add_argument("--oneshot", action="store_true",
                        help="faz uma captura e encerra (útil para ligar a um atalho do sistema)")
    parser.add_argument("--startup", action="store_true", help="aberto junto com o Windows: fica quieto na bandeja")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)  # usado pelo build
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.selftest:
        return selftest()

    command = next((name for name in ("capture", "ocr", "record", "history") if getattr(args, name)), "")
    if args.oneshot:
        command = command or "capture"

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Klick")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    theme.load_fonts()
    app.setFont(theme.font(13))
    app.setStyleSheet(theme.app_stylesheet())
    app.setProperty("klick_oneshot", args.oneshot)

    server = None
    if not args.oneshot:
        if send_to_running(command):
            return 0
        server = InstanceServer(parent=app)
        if not server.listen():
            log.warning("Não foi possível garantir instância única")

    klick = KlickApp(app)
    if server is not None:
        server.received.connect(klick.handle_command)
    if not args.oneshot:
        klick.run()
    if command:
        klick.handle_command(command)
    elif not args.startup:
        klick.announce()
    code = app.exec()
    destroy_windows(app)
    return code


def selftest() -> int:
    """Confere, no executável empacotado, que fontes, ícones e os dois motores de OCR funcionam.

    Sai com 0 se tudo leu o texto de teste; o código de saída diz o que falhou.
    """
    from PySide6.QtGui import QColor, QFont, QPainter

    app = QApplication(sys.argv[:1])
    theme.load_fonts()
    if "Barlow" not in theme.font(13).family():
        return 2
    if icons.pixmap("copy", theme.S500, 18, 1.0).isNull():
        return 3
    image = QImage(560, 90, QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    p = QPainter(image)
    f = QFont("Segoe UI")
    f.setPixelSize(30)
    p.setFont(f)
    p.setPen(QColor("#111111"))
    p.drawText(16, 58, "Pedido 48213 faturado")
    p.end()
    try:
        fast = ocr.recognize_words(image).result(timeout=60).text
        precise = ocr.recognize_precise(image).result(timeout=180).text
    except Exception:  # noqa: BLE001
        log.exception("selftest")
        return 4
    finally:
        app.processEvents()
    print(f"rápido: {fast!r} | preciso: {precise!r}")
    return 0 if "48213" in fast and "48213" in precise else 5


def destroy_windows(app: QApplication) -> None:
    """Apaga as janelas antes da QApplication.

    Janelas presas em ciclos de referência só seriam coletadas no fim do interpretador,
    depois do app, e o processo cairia com access violation ao sair.
    """
    # Só as janelas sem dono: popups (como a lista de um QComboBox) também são "top level",
    # mas morrem com o dono; apagar os dois derruba o processo.
    for widget in [w for w in app.topLevelWidgets() if w.parent() is None]:
        if shiboken6.isValid(widget):
            shiboken6.delete(widget)


if __name__ == "__main__":
    raise SystemExit(main())
