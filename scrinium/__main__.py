"""Entry point: python -m scrinium."""
import faulthandler
import logging
import sys
import threading
import traceback

from PyQt6.QtWidgets import QApplication

from scrinium import __app_name__, __version__
from scrinium.gui.main_window import MainWindow
from scrinium.gui.theme import STYLESHEET
from scrinium.utils import autostart
from scrinium.utils.logger import setup_logging
from scrinium.utils.paths import app_data_dir

log = logging.getLogger(__name__)

# Riferimento di modulo al file di faulthandler: deve restare aperto per
# tutta la vita del processo, altrimenti il crash nativo non verrebbe
# scritto.
_faulthandler_file = None


def _enable_faulthandler() -> None:
    """Abilita la scrittura di tracebacks C/Python in caso di crash nativo
    (segfault, abort PyQt, stack overflow) su un file dedicato."""
    global _faulthandler_file
    try:
        path = app_data_dir() / "faulthandler.log"
        _faulthandler_file = open(path, "a", buffering=1, encoding="utf-8")
        _faulthandler_file.write(
            f"\n===== Scrinium v{__version__} start =====\n"
        )
        _faulthandler_file.flush()
        faulthandler.enable(file=_faulthandler_file, all_threads=True)
    except Exception:
        log.exception("Impossibile abilitare faulthandler")


def _install_excepthooks() -> None:
    """Intercetta eccezioni non catturate (thread principale e secondari)
    e le scrive nel log, così non si perdono quando PyInstaller gira in
    modalità windowed (nessuna console)."""

    def _handle(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        msg = "".join(traceback.format_exception(exc_type, exc, tb))
        log.critical("Uncaught exception on main thread:\n%s", msg)

    def _handle_thread(args) -> None:
        msg = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        )
        log.critical(
            "Uncaught exception on thread %r:\n%s",
            getattr(args.thread, "name", "?"),
            msg,
        )

    sys.excepthook = _handle
    threading.excepthook = _handle_thread


def _log_aboutToQuit() -> None:
    # Stack trace di chi sta chiedendo la quit, così sappiamo sempre da
    # dove arriva una terminazione dell'applicazione.
    stack = "".join(traceback.format_stack())
    log.warning("QApplication.aboutToQuit — chiusura in corso\n%s", stack)


def main() -> int:
    app_data_dir().mkdir(parents=True, exist_ok=True)
    setup_logging()
    _enable_faulthandler()
    _install_excepthooks()
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
