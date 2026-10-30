import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":  # sem tela o Qt não acha as fontes do Windows sozinho (Segoe UI, Consolas)
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
# Preferências e histórico isolados: os testes nunca tocam nos dados reais do usuário.
_tmp = tempfile.mkdtemp(prefix="klick-tests-")
os.environ["KLICK_SETTINGS"] = os.path.join(_tmp, "settings.ini")
os.environ["KLICK_HISTORY_DIR"] = os.path.join(_tmp, "history")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    from klick.app import destroy_windows

    destroy_windows(app)
