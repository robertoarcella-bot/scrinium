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
        self.setMinimumSize(520, 360)
        # Aggiungi i pulsanti 'minimizza' e 'massimizza' nella title bar
        # (di default un QDialog ne è sprovvisto). Il backup gira in un
        # thread separato, quindi la finestra è liberamente minimizzabile.
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        # Modal non-bloccante a livello applicazione: il main window e la
        # tray restano comunque funzionanti (utile per mandare in tray).
        self.setModal(False)
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
        self.btn_minimize = QPushButton("Minimizza")
        self.btn_minimize.setToolTip(
            "Riduce a icona la finestra: il backup continua in background."
        )
        self.btn_hide_tray = QPushButton("Nella tray")
        self.btn_hide_tray.setToolTip(
            "Nasconde la finestra nella barra di sistema. Cliccare l'icona "
            "Scrinium in basso a destra per riaprirla."
        )
        self.btn_close = QPushButton("Chiudi")
        self.btn_close.setEnabled(False)
        btns.addWidget(self.btn_pause)
        btns.addWidget(self.btn_resume)
        btns.addWidget(self.btn_stop)
        btns.addStretch(1)
        btns.addWidget(self.btn_minimize)
        btns.addWidget(self.btn_hide_tray)
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
        self.btn_minimize.clicked.connect(self.showMinimized)
        self.btn_hide_tray.clicked.connect(self._on_hide_tray)
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
        # Il log widget non riceve ogni singolo file (sarebbero migliaia di
        # righe al secondo): solo cambi di fase e milestone ogni 1000 file.
        self._maybe_log(prog)

    def _maybe_log(self, prog: Progress) -> None:
        if not hasattr(self, "_last_logged_phase"):
            self._last_logged_phase = ""
            self._last_logged_milestone = -1
            self._last_logged_errors = 0
        if prog.phase and prog.phase != self._last_logged_phase:
            self.log.appendPlainText(
                f"→ Fase: {prog.phase}  ({prog.message})"
            )
            self._last_logged_phase = prog.phase
        milestone = prog.files_done // 1000
        if milestone > self._last_logged_milestone and prog.files_done > 0:
            self.log.appendPlainText(
                f"… {prog.files_done}/{prog.files_total} file  •  "
                f"{_fmt_bytes(prog.bytes_done)}/{_fmt_bytes(prog.bytes_total)}"
            )
            self._last_logged_milestone = milestone
        if prog.errors > self._last_logged_errors:
            self.log.appendPlainText(
                f"⚠ Errori cumulativi: {prog.errors} (vedi report finale per elenco)"
            )
            self._last_logged_errors = prog.errors

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

    def _on_hide_tray(self) -> None:
        """Nasconde la finestra di backup e la main window, portando
        Scrinium nella barra di sistema. Il worker del backup continua a
        girare in thread separato.
        """
        self.hide()
        parent = self.parent()
        if parent is not None and hasattr(parent, "_hide_to_tray"):
            parent._hide_to_tray()

    def closeEvent(self, event) -> None:
        # Se il backup sta ancora girando, la chiusura della finestra con la
        # X NON deve fermarlo: la portiamo nella tray. Così l'utente può
        # liberare lo schermo senza perdere l'avanzamento.
        if self.thread.isRunning() and not self.worker.control.should_stop:
            event.ignore()
            self._on_hide_tray()
            return
        if self.thread.isRunning():
            self.worker.stop()
            self.thread.quit()
            self.thread.wait(3000)
        super().closeEvent(event)
