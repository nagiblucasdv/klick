"""Uma instância só: abrir o Klick de novo repassa o comando para a que já está na bandeja.

Sem isso, o atalho do Menu Iniciar e o "iniciar com o Windows" criariam dois ícones
e dois listeners disputando o PrintScreen.
"""

from __future__ import annotations

import getpass

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

CONNECT_TIMEOUT_MS = 300


def server_name() -> str:
    return f"klick-{getpass.getuser()}"


def send_to_running(command: str, name: str | None = None) -> bool:
    """Entrega o comando à instância que já roda. False se não houver nenhuma."""
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    socket.write(command.encode() + b"\n")
    socket.flush()
    # O servidor fecha depois de ler; fechar antes disso pode perder a mensagem no Windows.
    if socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
        socket.waitForDisconnected(1000)
    return True


class InstanceServer(QObject):
    received = Signal(str)

    def __init__(self, name: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self._name = name or server_name()
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

    def listen(self) -> bool:
        QLocalServer.removeServer(self._name)  # sobra de uma instância que travou (só importa fora do Windows)
        return self._server.listen(self._name)

    def close(self) -> None:
        self._server.close()

    def _on_connection(self) -> None:
        while (socket := self._server.nextPendingConnection()) is not None:
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(socket.deleteLater)
            self._read(socket)  # os dados podem ter chegado antes do connect acima

    def _read(self, socket: QLocalSocket) -> None:
        if not socket.canReadLine():
            return
        command = bytes(socket.readLine()).decode(errors="replace").rstrip("\n")
        socket.disconnectFromServer()
        self.received.emit(command)
