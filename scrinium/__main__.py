"""Entry point: python -m scrinium."""
import ctypes
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


def _opt_out_power_throttling() -> None:
    """Disattiva il power throttling (EcoQoS) su Windows 10/11.

    Senza questa chiamata, Windows può mettere i thread in modalità
    ``EcoQoS`` quando la finestra non è visibile (es. app in tray),
    rallentandoli e, in alcune configurazioni, sospendendo il processo.
    L'API ``SetProcessInformation(ProcessPowerThrottling)`` con state
    mask a 0 comunica a Windows: "questo processo non deve essere
    throttled, anche se sta in background".
    """
    if sys.platform != "win32":
        return
    try:
        # typedef struct _PROCESS_POWER_THROTTLING_STATE {
        #     ULONG Version;
        #     ULONG ControlMask;
        #     ULONG StateMask;
        # } PROCESS_POWER_THROTTLING_STATE;

        class _PowerThrottling(ctypes.Structure):
            _fields_ = [
                ("Version", ctypes.c_ulong),
                ("ControlMask", ctypes.c_ulong),
                ("StateMask", ctypes.c_ulong),
            ]

        PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
        PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
        ProcessPowerThrottling = 4  # PROCESS_INFORMATION_CLASS

        info = _PowerThrottling(
            Version=PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            ControlMask=PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            StateMask=0,  # 0 = disabilita throttling
        )
        kernel32 = ctypes.windll.kernel32
        kernel32.SetProcessInformation.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ulong,
        ]
        kernel32.SetProcessInformation.restype = ctypes.c_int
        handle = kernel32.GetCurrentProcess()
        ok = kernel32.SetProcessInformation(
            handle, ProcessPowerThrottling, ctypes.byref(info), ctypes.sizeof(info)
        )
        if ok:
            log.info("Power throttling: opt-out riuscito (EcoQoS disattivato)")
        else:
            err = ctypes.get_last_error()
            log.warning("SetProcessInformation ha fallito (err=%s)", err)
    except Exception:
        log.exception("Impossibile disattivare il power throttling")


def _acquire_system_wake_lock() -> None:
    """Impedisce a Windows di mettere il sistema in sleep mentre
    Scrinium è in esecuzione. Lock persistente per l'intera vita del
    processo: viene ripulito automaticamente alla terminazione."""
    if sys.platform != "win32":
        return
    try:
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
        log.info("Wake lock di sistema acquisito (persistente)")
    except Exception:
        log.exception("Impossibile acquisire il wake lock di sistema")


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
    _opt_out_power_throttling()
    _acquire_system_wake_lock()
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
