"""QThread wrapper per eseguire un BackupEngine senza bloccare la GUI."""
from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from scrinium.core.engine import BackupEngine, BackupReport, Progress, RunControl
from scrinium.core.profile import BackupProfile

log = logging.getLogger(__name__)


class BackupWorker(QObject):
    progress = pyqtSignal(object)  # Progress
    finished = pyqtSignal(object)  # BackupReport

    def __init__(self, profile: BackupProfile):
        super().__init__()
        self.profile = profile
        self.control = RunControl()

    def run(self) -> None:
        try:
            engine = BackupEngine(
                self.profile,
                on_progress=self.progress.emit,
                control=self.control,
            )
            report = engine.run()
        except BaseException:
            # Qualsiasi eccezione (incluse KeyboardInterrupt/SystemExit che
            # potrebbero attraversare il thread) deve essere loggata prima
            # di propagarsi, altrimenti in modalità windowed il crash è
            # invisibile e trascina giù tutto il processo senza traccia.
            log.exception(
                "Eccezione non gestita nel worker di backup (profilo=%s)",
                self.profile.name,
            )
            # Segnaliamo comunque la fine al dialog, con un report fallito,
            # così l'interfaccia non resta bloccata in attesa.
            report = BackupReport()
            report.files_failed = 1
            report.failures.append((self.profile.name, "Errore interno del worker"))
            self.finished.emit(report)
            return
        self.finished.emit(report)

    def pause(self) -> None:
        self.control.pause()

    def resume(self) -> None:
        self.control.resume()

    def stop(self) -> None:
        self.control.stop()


def start_worker(profile: BackupProfile) -> tuple[QThread, BackupWorker]:
    thread = QThread()
    worker = BackupWorker(profile)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker
