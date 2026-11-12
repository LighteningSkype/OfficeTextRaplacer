"""应用启动逻辑（供 main.py 与 python -m app 共用）。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .core.config import APP_TITLE
from .ui import theme
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("OfficeTextReplacer")
    app.setWindowIcon(theme.app_icon())
    theme.apply_theme(app)

    window = MainWindow()
    window.show()
    return app.exec()
