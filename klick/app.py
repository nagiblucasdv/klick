"""Ponto de entrada: ícone na bandeja, atalho global e sessão de captura."""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import Future

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QImage
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from klick import __version__, config, ocr
from klick.actions import Action, copy_image, copy_text, save_image
from klick.capture import grab_screens
from klick.hotkeys import HotkeyListener
from klick.icon import app_icon
from klick.overlay import CaptureSession

log = logging.getLogger("klick")

PREVIEW_CHARS = 60


class KlickApp(QObject):
    # Emitido da thread do OCR; a conexão queued traz o resultado para a thread do Qt.
    _ocrDone = Signal(str, str)  # texto, erro

    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self._session: CaptureSession | None = None
        self._ocr_pending = False

        self._tray = QSystemTrayIcon(app_icon(), self)
        self._tray.setToolTip(f"Klick {__version__}")
        menu = QMenu()
        menu.addAction(QAction("Capturar área", menu, triggered=lambda: self.start_capture()))
        menu.addAction(QAction("Copiar texto (OCR)", menu, triggered=lambda: self.start_capture(Action.OCR)))
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

    def quit(self) -> None:
        self._hotkeys.stop()
        self._tray.hide()
        self._app.quit()

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
        if self._app.property("klick_oneshot") and self._session is None and not self._ocr_pending:
            self.quit()

    def _on_finished(self, action: Action, image: QImage) -> None:
        try:
            if action is Action.COPY:
                copy_image(image)
                self._notify("Copiado para a área de transferência")
            elif action is Action.SAVE:
                path = save_image(image)
                if path:
                    self._notify(f"Salvo em {path}")
            elif action is Action.OCR:
                self._start_ocr(image)
        except OSError as exc:
            self._warn(f"{exc}\nEscolha outra pasta e tente de novo.")
        finally:
            self._end_session()

    def _start_ocr(self, image: QImage) -> None:
        self._ocr_pending = True
        ocr.recognize(image, config.ocr_language()).add_done_callback(self._emit_ocr_result)

    def _emit_ocr_result(self, future: Future[str]) -> None:
        try:
            self._ocrDone.emit(future.result(), "")
        except Exception as exc:  # noqa: BLE001 - qualquer falha do WinRT vira aviso
            log.warning("OCR falhou", exc_info=exc)
            self._ocrDone.emit("", str(exc) or type(exc).__name__)

    def _on_ocr_done(self, text: str, error: str) -> None:
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
        self._maybe_quit()

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

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.start_capture()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="klick", description="Captura de tela por seleção de área.")
    parser.add_argument("--capture", action="store_true", help="abre a seleção imediatamente")
    parser.add_argument("--ocr", action="store_true", help="abre a seleção em modo OCR direto")
    parser.add_argument("--oneshot", action="store_true",
                        help="captura uma vez e encerra (útil para ligar a um atalho do sistema)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Klick")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    app.setProperty("klick_oneshot", args.oneshot)

    klick = KlickApp(app)
    if not args.oneshot:
        klick.run()
    if args.ocr:
        klick.start_capture(Action.OCR)
    elif args.capture or args.oneshot:
        klick.start_capture()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
