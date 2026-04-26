"""Dialog di preferenze dell'applicazione (autostart, modalità schedulazione)."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
)

from scrinium.utils import autostart, preferences


class PreferencesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._main_window = parent  # MainWindow, per applicare il cambio modalità
        self.prefs = preferences.load()

        self.setWindowTitle("Preferenze Scrinium")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)

        # ---- Sezione: Avvio automatico -----------------------------------
        title = QLabel("<h3 style='color:#1e3a8a;'>Comportamento all'avvio</h3>")
        layout.addWidget(title)

        self.chk_autostart = QCheckBox(
            "Avvia Scrinium automaticamente all'accensione di Windows"
        )
        self.chk_autostart.setChecked(autostart.is_enabled())
        layout.addWidget(self.chk_autostart)

        hint = QLabel(
            "<p style='color:#64748b; font-size:11px;'>"
            "Quando attivo, Scrinium parte in background al login di Windows "
            "e resta sempre disponibile nella barra di sistema (tray). "
            "Non richiede privilegi di amministratore: la preferenza è "
            "salvata nel profilo utente corrente."
            "</p>"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ---- Sezione: Modalità schedulazione -----------------------------
        layout.addWidget(QLabel(
            "<h3 style='color:#1e3a8a;'>Modalità di schedulazione</h3>"
        ))

        sched_box = QGroupBox()
        sched_layout = QVBoxLayout(sched_box)

        self.rb_task = QRadioButton(
            "Windows Task Scheduler (consigliata)"
        )
        self.rb_task.setEnabled(sys.platform == "win32")
        sched_layout.addWidget(self.rb_task)
        sched_layout.addWidget(_hint(
            "I backup vengono eseguiti dal Task Scheduler di Windows: il PC "
            "si <b>sveglia automaticamente dallo sleep</b> all'orario previsto, "
            "il backup parte anche se Scrinium è chiuso o congelato, e "
            "un'esecuzione mancata (PC spento) viene recuperata appena la "
            "macchina torna disponibile.<br>"
            "Sono supportati i pattern cron «M H * * *» (giornaliero), "
            "«M H * * D» (settimanale), «M H D * *» (mensile), "
            "«M * * * *» (orario)."
        ))

        self.rb_in_app = QRadioButton(
            "Schedulatore integrato (legacy: solo finché Scrinium è aperto)"
        )
        sched_layout.addWidget(self.rb_in_app)
        sched_layout.addWidget(_hint(
            "I backup vengono lanciati da Scrinium stesso. Funziona <b>solo "
            "mentre l'app è aperta e il PC è sveglio</b>: se Windows è in "
            "sleep o Scrinium è chiuso/freezato, il trigger viene perso. "
            "Disponibile per chi non vuole registrare task nel sistema."
        ))

        group = QButtonGroup(self)
        group.addButton(self.rb_task)
        group.addButton(self.rb_in_app)
        if self.prefs.scheduler_mode == "in_app":
            self.rb_in_app.setChecked(True)
        else:
            self.rb_task.setChecked(True)

        layout.addWidget(sched_box)

        # ---- Bottoni -----------------------------------------------------
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self) -> None:
        # Autostart
        want = self.chk_autostart.isChecked()
        have = autostart.is_enabled()
        if want != have:
            ok = autostart.enable() if want else autostart.disable()
            if not ok:
                QMessageBox.warning(
                    self,
                    "Operazione non riuscita",
                    "Non è stato possibile modificare l'avvio automatico. "
                    "Verifica di avere i permessi sul registro utente.",
                )
                return

        # Modalità schedulazione: se cambiata, applicala via MainWindow
        # (così smonta APScheduler / sincronizza Task Scheduler in modo
        # coerente).
        new_mode = "in_app" if self.rb_in_app.isChecked() else "task_scheduler"
        if new_mode != self.prefs.scheduler_mode and self._main_window is not None:
            try:
                self._main_window.apply_scheduler_mode_change(new_mode)
            except Exception:
                QMessageBox.warning(
                    self,
                    "Modalità schedulazione",
                    "Si è verificato un errore applicando il cambio modalità. "
                    "Controllare il log per i dettagli.",
                )
                return

        self.accept()


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        "color: #64748b; font-size: 11px; margin-left: 22px; margin-bottom: 6px;"
    )
    return lbl
