"""Entry point: python -m scrinium."""
import logging
import sys
import traceback

from PyQt6.QtWidgets import QApplication

from scrinium import __app_name__, __version__
from scrinium.gui.main_window import MainWindow
from scrinium.gui.theme import STYLESHEET
from scrinium.utils import autostart
from scrinium.utils.logger import setup_logging
from scrinium.utils.paths import app_data_dir

log = logging.getLogger(__name__)


def _log_aboutToQuit() -> None:
    # Stack trace di chi sta chiedendo la quit, così sappiamo sempre da
    # dove arriva una terminazione dell'applicazione.
    stack = "".join(traceback.format_stack())
    log.warning("QApplication.aboutToQuit — chiusura in corso\n%s", stack)


def main() -> int:
    app_data_dir().mkdir(parents=True, exist_ok=True)
    setup_logging()
    log.info("Scrinium v%s avvio (argv=%s)", __version__, sys.argv)

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName(__app_name__)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    # Consente a Scrinium di vivere solo nella tray (main window nascosta)
    # senza uscire quando si chiude l'ultima finestra.
    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(_log_aboutToQuit)

    window = MainWindow()
    # Se lanciato all'avvio di Windows (--startup), parte silenziosamente
    # nella tray senza mostrare la main window.
    if autostart.is_startup_launch() and window.tray is not None:
        log.info("Avvio in modalità --startup: solo tray, finestra nascosta")
        window._tray_message_shown = True  # niente toast al boot
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
