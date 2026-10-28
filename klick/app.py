"""Ponto de entrada: ícone na bandeja, atalho global e sessão de captura."""

from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction, QImage
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from klick import __version__, config
from klick.actions import Action, copy_image, save_image
from klick.capture import grab_screens
from klick.hotkeys import HotkeyListener
from klick.icon import app_icon
from klick.overlay import CaptureSession

log = logging.getLogger("klick")


class KlickApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self._session: CaptureSession | None = None

        self._tray = QSystemTrayIcon(app_icon(), self)
        self._tray.setToolTip(f"Klick {__version__}")
        menu = QMenu()
        capture = QAction("Capturar área", menu, triggered=lambda: self.start_capture())
        quit_ = QAction("Sair", menu, triggered=lambda: self.quit())
        menu.addAction(capture)
        menu.addSeparator()
        menu.addAction(quit_)
        self._menu = menu  # mantém referência viva
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)

        self._hotkeys = HotkeyListener(config.hotkeys())
        self._hotkeys.triggered.connect(self._on_hotkey)

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
        if self._app.property("klick_oneshot"):
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
        except OSError as exc:
            QMessageBox.warning(None, "Klick", f"{exc}\nEscolha outra pasta e tente de novo.")
        finally:
            self._end_session()

    def _notify(self, message: str) -> None:
        log.info(message)
        if self._tray.isVisible():
            self._tray.showMessage("Klick", message, app_icon(), 1500)

    def _on_hotkey(self, name: str) -> None:
        if name == "capture":
            self.start_capture()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.start_capture()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="klick", description="Captura de tela por seleção de área.")
    parser.add_argument("--capture", action="store_true", help="abre a seleção imediatamente")
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
    if args.capture or args.oneshot:
        klick.start_capture()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
