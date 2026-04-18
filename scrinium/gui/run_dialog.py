"""Dialog che mostra l'avanzamento di un backup in corso."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from scrinium.core.engine import BackupReport, Progress
from scrinium.core.profile import BackupProfile
from scrinium.gui.worker import BackupWorker


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class RunDialog(QDialog):
    def __init__(self, profile: BackupProfile, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Backup: {profile.name}")
        self.resize(700, 480)
        self.profile = profile
        self.report: BackupReport | None = None

        layout = QVBoxLayout(self)

        self.lbl_phase = QLabel("Preparazione...")
        self.lbl_phase.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.lbl_phase)

        self.lbl_current = QLabel("")
        self.lbl_current.setWordWrap(True)
        layout.addWidget(self.lbl_current)

        self.bar_files = QProgressBar()
        self.bar_bytes = QProgressBar()
        layout.addWidget(QLabel("Progresso file"))
        layout.addWidget(self.bar_files)
        layout.addWidget(QLabel("Progresso byte"))
        layout.addWidget(self.bar_bytes)

        self.lbl_stats = QLabel("")
        layout.addWidget(self.lbl_stats)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        layout.addWidget(self.log, 1)

        btns = QHBoxLayout()
        self.btn_pause = QPushButton("Pausa")
        self.btn_resume = QPushButton("Riprendi")
        self.btn_resume.setEnabled(False)
        self.btn_stop = QPushButton("Annulla")
        self.btn_close = QPushButton("Chiudi")
        self.btn_close.setEnabled(False)
        btns.addWidget(self.btn_pause)
        btns.addWidget(self.btn_resume)
        btns.addWidget(self.btn_stop)
        btns.addStretch(1)
        btns.addWidget(self.btn_close)
        layout.addLayout(btns)

        # Thread + worker
        self.thread = QThread(self)
        self.worker = BackupWorker(profile)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.thread.quit)

        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_resume.clicked.connect(self._on_resume)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_close.clicked.connect(self.accept)

        self.thread.start()

    # ---- Slot ----
    def _on_progress(self, prog: Progress) -> None:
        self.lbl_phase.setText(f"Fase: {prog.phase}  —  {prog.message}")
        self.lbl_current.setText(prog.current_file)
        if prog.files_total:
            self.bar_files.setMaximum(prog.files_total)
            self.bar_files.setValue(prog.files_done)
        if prog.bytes_total:
            # Usa scala in KB per evitare overflow su bar int32
            self.bar_bytes.setMaximum(max(1, prog.bytes_total // 1024))
            self.bar_bytes.setValue(prog.bytes_done // 1024)
        self.lbl_stats.setText(
            f"File: {prog.files_done}/{prog.files_total}  •  "
            f"Byte: {_fmt_bytes(prog.bytes_done)}/{_fmt_bytes(prog.bytes_total)}  •  "
            f"Errori: {prog.errors}"
        )
        if prog.current_file:
            self.log.appendPlainText(f"[{prog.phase}] {prog.current_file}")

    def _on_finished(self, report: BackupReport) -> None:
        self.report = report
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_close.setEnabled(True)
        summary = (
            f"Stato: {report.status.upper()}\n"
            f"Durata: {report.duration_sec:.1f} s\n"
            f"Copiati: {report.files_copied}\n"
            f"Aggiornati: {report.files_updated}\n"
            f"Saltati: {report.files_skipped}\n"
            f"Eliminati: {report.files_deleted}\n"
            f"Falliti: {report.files_failed}\n"
            f"Byte copiati: {_fmt_bytes(report.bytes_copied)}"
        )
        self.log.appendPlainText("\n" + "-" * 60 + "\n" + summary)
        if report.failures:
            self.log.appendPlainText("\nFallimenti (primi 20):")
            for path, err in report.failures[:20]:
                self.log.appendPlainText(f"  {path}: {err}")

    def _on_pause(self) -> None:
        self.worker.pause()
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(True)

    def _on_resume(self) -> None:
        self.worker.resume()
        self.btn_pause.setEnabled(True)
        self.btn_resume.setEnabled(False)

    def _on_stop(self) -> None:
        ans = QMessageBox.question(
            self,
            "Annullare?",
            "Interrompere il backup in corso? I file già copiati restano in destinazione.",
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.worker.stop()

    def closeEvent(self, event) -> None:
        if self.thread.isRunning():
            self.worker.stop()
            self.thread.quit()
            self.thread.wait(3000)
        super().closeEvent(event)
