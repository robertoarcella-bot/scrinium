"""Dialog di preferenze dell'applicazione (autostart, ecc.)."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from scrinium.utils import autostart


class PreferencesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferenze Scrinium")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

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
            "Le schedulazioni automatiche vengono eseguite senza che tu "
            "debba ricordarti di aprire l'applicazione.<br><br>"
            "Non richiede privilegi di amministratore: la preferenza è "
            "salvata nel profilo utente corrente."
            "</p>"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self) -> None:
        want = self.chk_autostart.isChecked()
        have = autostart.is_enabled()
        if want == have:
            self.accept()
            return
        ok = autostart.enable() if want else autostart.disable()
        if not ok:
            QMessageBox.warning(
                self,
                "Operazione non riuscita",
                "Non è stato possibile modificare l'avvio automatico. "
                "Verifica di avere i permessi sul registro utente.",
            )
            return
        self.accept()
