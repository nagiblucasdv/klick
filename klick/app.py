"""Ponto de entrada: ícone na bandeja, atalho global e sessão de captura."""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import Future
from pathlib import Path

import shiboken6
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QImage
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from klick import __version__, config, ocr
from klick.actions import Action, copy_file, copy_image, copy_text, save_image
from klick.capture import Selection, grab_screens
from klick.editor import EditorWindow
from klick.history import History
from klick.history_ui import HistoryWindow
from klick.hotkeys import HotkeyListener
from klick.icon import app_icon
from klick.overlay import CaptureSession
from klick.recorder import Recorder, RecordFormat
from klick.recording_ui import RecordingIndicator
from klick.single import InstanceServer, send_to_running

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
        self._history = history if history is not None else History()
        self._history_window: HistoryWindow | None = None

        self._recorder = Recorder(self)
        self._recorder.converting.connect(lambda: self._indicator and self._indicator.set_status("Gerando GIF…"))
        self._recorder.finished.connect(self._on_record_finished)
        self._recorder.failed.connect(self._on_record_failed)
        self._indicator: RecordingIndicator | None = None

        self._tray = QSystemTrayIcon(app_icon(), self)
        self._tray.setToolTip(f"Klick {__version__}")
        menu = QMenu()
        menu.addAction(QAction("Capturar área", menu, triggered=lambda: self.start_capture()))
        menu.addAction(QAction("Copiar texto (OCR)", menu, triggered=lambda: self.start_capture(Action.OCR)))
        self._record_action = QAction("Gravar área", menu, triggered=lambda: self.toggle_recording())
        menu.addAction(self._record_action)
        menu.addSeparator()
        menu.addAction(QAction("Histórico…", menu, triggered=lambda: self.show_history()))
        keep = QAction("Guardar histórico", menu, checkable=True, checked=config.history_enabled())
        keep.toggled.connect(config.set_history_enabled)
        menu.addAction(keep)
        menu.addSeparator()
        menu.addAction(QAction("Sair", menu, triggered=lambda: self.quit()))
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
            self._history_window = HistoryWindow(self._history)
        self._history_window.refresh()
        self._history_window.show()
        self._history_window.raise_()
        self._history_window.activateWindow()

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
        if self._tray.isVisible():
            self._tray.showMessage("Klick está na bandeja", f"Aperte {key} para capturar uma área.",
                                   app_icon(), 4000)

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
                and not self._recorder.busy and not self._editors)
        if self._app.property("klick_oneshot") and idle:
            self.quit()

    def _on_finished(self, action: Action, selection: Selection) -> None:
        try:
            if action is Action.OCR:
                self._start_ocr(selection.image)
            elif action is Action.EDIT:
                self._open_editor(selection)
            elif action in (Action.RECORD, Action.GIF):
                self._start_recording(selection, RecordFormat.GIF if action is Action.GIF else RecordFormat.MP4)
            else:
                self._deliver(action, selection.image)
        finally:
            self._end_session()

    def _deliver(self, action: Action, image: QImage, source: str | None = None) -> None:
        """Copia ou salva a imagem final (direto da seleção ou vinda do editor)."""
        try:
            if action is Action.COPY:
                copy_image(image)
                self._notify("Copiado para a área de transferência")
            elif action is Action.SAVE:
                path = save_image(image)
                if not path:
                    return
                self._notify(f"Salvo em {path}")
        except OSError as exc:
            self._warn(f"{exc}\nEscolha outra pasta e tente de novo.")
            return
        self._history.add(image, source or action.value)

    # --- editor ------------------------------------------------------------

    def _open_editor(self, selection: Selection) -> None:
        editor = EditorWindow(selection.image, selection.device_pixel_ratio)
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

    # --- OCR ---------------------------------------------------------------

    def _start_ocr(self, image: QImage) -> None:
        self._ocr_pending = True
        ocr.recognize(image, config.ocr_language()).add_done_callback(
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
            self._notify("Nenhum texto encontrado na área. Tente selecionar uma área maior.")
        else:
            copy_text(text)
            preview = " ".join(text.split())
            if len(preview) > PREVIEW_CHARS:
                preview = preview[:PREVIEW_CHARS] + "…"
            self._notify(f"Texto copiado: {preview}")
            self._history.add(image, Action.OCR.value, text=text)
        self._maybe_quit()

    # --- gravação ----------------------------------------------------------

    def _start_recording(self, selection: Selection, fmt: RecordFormat) -> None:
        indicator = RecordingIndicator(selection.logical, self._recorder.elapsed)
        indicator.stopRequested.connect(self._recorder.stop)
        self._indicator = indicator

        def begin() -> None:
            self._recorder.start(selection.rect, fmt, config.save_dir())
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
        self._notify(f"Gravação salva em {path} (copiada, é só colar)")
        self._maybe_quit()

    def _on_record_failed(self, message: str) -> None:
        self._close_indicator()
        self._warn(message)
        self._maybe_quit()

    # --- avisos e eventos --------------------------------------------------

    def _notify(self, message: str) -> None:
        log.info(message)
        if self._tray.isVisible():
            self._tray.showMessage("Klick", message, app_icon(), 1500)

    def _warn(self, message: str) -> None:
        log.warning(message)
        if self._tray.isVisible():
            self._tray.showMessage("Klick", message, QSystemTrayIcon.MessageIcon.Warning, 4000)
        else:
            QMessageBox.warning(None, "Klick", message)

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
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    command = next((name for name in ("capture", "ocr", "record", "history") if getattr(args, name)), "")
    if args.oneshot:
        command = command or "capture"

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Klick")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
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


def destroy_windows(app: QApplication) -> None:
    """Apaga as janelas antes da QApplication.

    Janelas presas em ciclos de referência só seriam coletadas no fim do interpretador,
    depois do app, e o processo cairia com access violation ao sair.
    """
    for widget in app.topLevelWidgets():
        shiboken6.delete(widget)


if __name__ == "__main__":
    raise SystemExit(main())
