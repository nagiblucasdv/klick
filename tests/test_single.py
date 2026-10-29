import subprocess
import sys
import uuid

from klick.single import InstanceServer, send_to_running
from test_recorder import wait_for


def test_without_running_instance_send_fails(qapp):
    assert not send_to_running("capture", name=f"klick-test-{uuid.uuid4().hex}")


def send_from_other_process(command: str, name: str) -> subprocess.Popen:
    # Outro processo, como no uso real (abrir o Klick de novo pelo Menu Iniciar).
    code = f"from klick.single import send_to_running; raise SystemExit(0 if send_to_running({command!r}, {name!r}) else 1)"
    return subprocess.Popen([sys.executable, "-c", code])


def test_second_instance_forwards_command(qapp):
    name = f"klick-test-{uuid.uuid4().hex}"
    server = InstanceServer(name)
    assert server.listen()
    received = []
    server.received.connect(received.append)

    for command in ("ocr", ""):
        client = send_from_other_process(command, name)
        assert wait_for(lambda: client.poll() is not None, 10000)
        assert client.returncode == 0
    assert wait_for(lambda: len(received) == 2, 2000)
    assert received == ["ocr", ""]
    server.close()
