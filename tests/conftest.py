import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Preferências e histórico isolados: os testes nunca tocam nos dados reais do usuário.
_tmp = tempfile.mkdtemp(prefix="klick-tests-")
os.environ["KLICK_SETTINGS"] = os.path.join(_tmp, "settings.ini")
os.environ["KLICK_HISTORY_DIR"] = os.path.join(_tmp, "history")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])
