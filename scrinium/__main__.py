"""Entry point: python -m scrinium."""
import sys

from PyQt6.QtWidgets import QApplication

from scrinium import __app_name__
from scrinium.gui.main_window import MainWindow
from scrinium.gui.theme import STYLESHEET
from scrinium.utils.logger import setup_logging
from scrinium.utils.paths import app_data_dir


def main() -> int:
    app_data_dir().mkdir(parents=True, exist_ok=True)
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName(__app_name__)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
