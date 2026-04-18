"""QThread wrapper per eseguire un BackupEngine senza bloccare la GUI."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from scrinium.core.engine import BackupEngine, BackupReport, Progress, RunControl
from scrinium.core.profile import BackupProfile


class BackupWorker(QObject):
    progress = pyqtSignal(object)  # Progress
    finished = pyqtSignal(object)  # BackupReport

    def __init__(self, profile: BackupProfile):
        super().__init__()
        self.profile = profile
        self.control = RunControl()

    def run(self) -> None:
        engine = BackupEngine(
            self.profile,
            on_progress=self.progress.emit,
            control=self.control,
        )
        report = engine.run()
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
