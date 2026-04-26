"""Dialog di modifica profilo con descrizioni chiare di ogni opzione."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scrinium.core.profile import BackupProfile
from scrinium.core.scheduler import SCHEDULE_PRESETS, cron_is_valid


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #666; font-size: 11px;")
    return lbl


class ProfileEditor(QDialog):
    """Editor di un profilo, con esplicita indicazione di cosa fa ciascuna opzione."""

    def __init__(self, profile: BackupProfile | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Profilo di backup")
        self.profile = profile or BackupProfile(name="", source="", destination="")

        # Adatta la dimensione allo schermo disponibile (evita che i pulsanti
        # escano fuori da monitor piccoli o con scaling DPI alto).
        screen = self.screen() or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        w = min(720, avail.width() - 80) if avail else 720
        h = min(720, avail.height() - 120) if avail else 720
        self.resize(max(560, w), max(420, h))

        # Layout principale: scroll area + pulsanti fissi in basso
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        main.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setContentsMargins(16, 16, 16, 16)

        # -- Nome --
        self.ed_name = QLineEdit(self.profile.name)
        self.ed_name.setPlaceholderText("Es: Fascicoli 2026 -> disco esterno")
        form.addRow("Nome del profilo", self.ed_name)
        form.addRow("", _hint("Un'etichetta chiara per riconoscere il backup nell'elenco."))

        # -- Sorgente --
        src_row = QHBoxLayout()
        self.ed_src = QLineEdit(self.profile.source)
        btn_src = QPushButton("Sfoglia...")
        btn_src.clicked.connect(self._pick_source)
        src_row.addWidget(self.ed_src)
        src_row.addWidget(btn_src)
        src_widget = QWidget()
        src_widget.setLayout(src_row)
        form.addRow("Cartella sorgente", src_widget)
        form.addRow("", _hint("La cartella da cui copiare i dati (incluse tutte le sottocartelle)."))

        # -- Destinazione --
        dst_row = QHBoxLayout()
        self.ed_dst = QLineEdit(self.profile.destination)
        btn_dst = QPushButton("Sfoglia...")
        btn_dst.clicked.connect(self._pick_dest)
        dst_row.addWidget(self.ed_dst)
        dst_row.addWidget(btn_dst)
        dst_widget = QWidget()
        dst_widget.setLayout(dst_row)
        form.addRow("Cartella destinazione", dst_widget)
        form.addRow(
            "",
            _hint(
                "La cartella dove salvare la copia. Può essere sullo stesso PC, "
                "su un disco esterno o un percorso di rete."
            ),
        )

        # -- Modalità (CHIAREZZA su cosa fa) --
        self.cb_mode = QComboBox()
        self.cb_mode.addItem("Copia completa (sovrascrive sempre)", "full")
        self.cb_mode.addItem("Incrementale (solo nuovi/modificati, non cancella)", "incremental")
        self.cb_mode.addItem("Mirror (copia identica 1:1: cancella i file rimossi in sorgente)", "mirror")
        idx = self.cb_mode.findData(self.profile.mode)
        self.cb_mode.setCurrentIndex(max(0, idx))
        self.cb_mode.currentIndexChanged.connect(self._update_mode_hint)
        form.addRow("Modalità", self.cb_mode)
        self.lbl_mode_hint = _hint("")
        form.addRow("", self.lbl_mode_hint)
        self._update_mode_hint()

        # -- Criterio di confronto --
        self.cb_compare = QComboBox()
        self.cb_compare.addItem("Veloce (dimensione + data modifica)", "size_mtime")
        self.cb_compare.addItem("Sicuro (hash SHA-256)", "hash")
        idx = self.cb_compare.findData(self.profile.compare)
        self.cb_compare.setCurrentIndex(max(0, idx))
        self.cb_compare.currentIndexChanged.connect(self._update_compare_hint)
        form.addRow("Criterio di confronto", self.cb_compare)
        self.lbl_compare_hint = _hint("")
        form.addRow("", self.lbl_compare_hint)
        self._update_compare_hint()

        # -- Verifica hash post-copia --
        self.chk_verify = QCheckBox("Verifica hash SHA-256 dopo ogni copia")
        self.chk_verify.setChecked(self.profile.verify_hash_after_copy)
        form.addRow("Verifica integrità", self.chk_verify)
        form.addRow(
            "",
            _hint(
                "Ricalcola l'hash del file copiato e lo confronta con quello sorgente. "
                "Se diverso, il file viene ricopiato (fino a esaurire i tentativi). "
                "Raccomandato su dischi esterni."
            ),
        )

        # -- Retry --
        self.sp_retries = QSpinBox()
        self.sp_retries.setRange(1, 10)
        self.sp_retries.setValue(self.profile.max_retries)
        form.addRow("Tentativi massimi per file", self.sp_retries)
        form.addRow(
            "",
            _hint(
                "Se la copia di un file fallisce, viene ripetuta automaticamente. "
                "Il ritardo fra un tentativo e l'altro raddoppia ogni volta (backoff esponenziale)."
            ),
        )

        # -- Throttling --
        self.sp_throttle = QDoubleSpinBox()
        self.sp_throttle.setRange(0.0, 2048.0)
        self.sp_throttle.setDecimals(1)
        self.sp_throttle.setSuffix(" MB/s")
        self.sp_throttle.setValue(self.profile.throttle_mb_per_sec)
        form.addRow("Limite velocità (0 = nessun limite)", self.sp_throttle)
        form.addRow(
            "",
            _hint(
                "Limita la velocità di scrittura per evitare di saturare disco e rete. "
                "Impostare 0 per massima velocità."
            ),
        )

        # -- Modalità cloud --
        self.chk_cloud = QCheckBox(
            "Modalità cloud (Google Drive, OneDrive, iCloud...)"
        )
        self.chk_cloud.setChecked(self.profile.cloud_pace_mode)
        form.addRow("Destinazione cloud", self.chk_cloud)
        form.addRow(
            "",
            _hint(
                "Attiva SE la destinazione è un'unità cloud (es. G:\\Drive condivisi). "
                "Introduce una breve pausa tra un file e l'altro e, in caso di "
                "errore «disco pieno» (cache locale saturata dal client cloud), "
                "attende alcuni minuti che la coda si smaltisca prima di "
                "riprovare, invece di fallire il file."
            ),
        )

        # -- Compressione --
        self.chk_compress = QCheckBox(
            "Comprimi i file in destinazione (formato .gz)"
        )
        self.chk_compress.setChecked(self.profile.compress)
        form.addRow("Compressione", self.chk_compress)
        form.addRow(
            "",
            _hint(
                "Ogni file viene salvato in destinazione come «<nome>.gz» "
                "(gzip standard). Riduce lo spazio occupato (molto su file di "
                "testo/documenti, meno su PDF/immagini/video già compressi). "
                "Per ripristinare un singolo file: click destro in Esplora file → "
                "«Estrai tutto» (7-Zip, WinRAR, o utility simile). "
                "La verifica hash confronta il contenuto DECOMPRESSO con il "
                "sorgente, quindi l'integrità è garantita."
            ),
        )

        # -- Esclusioni --
        self.ed_excludes = QTextEdit()
        self.ed_excludes.setPlainText("\n".join(self.profile.exclude_patterns))
        self.ed_excludes.setFixedHeight(60)
        form.addRow("Esclusioni (uno per riga)", self.ed_excludes)
        form.addRow(
            "",
            _hint(
                "Pattern glob da escludere. Es: *.tmp, ~$*, Thumbs.db, .git, node_modules"
            ),
        )

        # -- Schedulazione --
        self.cb_preset = QComboBox()
        for label in SCHEDULE_PRESETS:
            self.cb_preset.addItem(label)
        self.cb_preset.currentIndexChanged.connect(self._apply_preset)
        form.addRow("Schedulazione (preset)", self.cb_preset)

        self.ed_cron = QLineEdit(self.profile.schedule_cron)
        self.ed_cron.setPlaceholderText("Espressione cron — es: 0 22 * * * (ogni giorno alle 22:00)")
        form.addRow("Espressione cron (avanzato)", self.ed_cron)
        form.addRow(
            "",
            _hint(
                "Lascia vuoto per nessuna schedulazione automatica. "
                "Formato: minuto ora giorno_mese mese giorno_settimana.<br>"
                "Su Windows i backup vengono affidati al <b>Task Scheduler</b> "
                "del sistema, che sveglia il PC dallo sleep e li esegue anche "
                "se Scrinium è chiuso (modalità modificabile in <i>Preferenze</i>)."
            ),
        )

        # -- Bottoni (fuori dalla scroll area, sempre visibili in basso) --
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        btn_wrap = QWidget()
        btn_layout = QHBoxLayout(btn_wrap)
        btn_layout.setContentsMargins(16, 8, 16, 12)
        btn_layout.addWidget(btns)
        main.addWidget(btn_wrap)

    # ---- Slot ----
    def _pick_source(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella sorgente", self.ed_src.text())
        if d:
            self.ed_src.setText(d)

    def _pick_dest(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella destinazione", self.ed_dst.text())
        if d:
            self.ed_dst.setText(d)

    def _update_mode_hint(self) -> None:
        mode = self.cb_mode.currentData()
        hints = {
            "full": "Ogni esecuzione riscrive TUTTI i file. Più lento, ma garantisce copia sempre fresca.",
            "incremental": "Copia solo i file NUOVI o MODIFICATI. I file eliminati dalla sorgente restano in destinazione. Veloce e sicuro.",
            "mirror": "La destinazione diventa IDENTICA alla sorgente. I file rimossi in sorgente vengono eliminati in destinazione. Usare con cautela.",
        }
        self.lbl_mode_hint.setText(hints[mode])

    def _update_compare_hint(self) -> None:
        c = self.cb_compare.currentData()
        hints = {
            "size_mtime": "Non legge il contenuto dei file: velocissimo. Raccomandato per uso quotidiano.",
            "hash": "Legge tutto il file per calcolare l'hash: più lento ma rileva anche modifiche che non alterano dimensione/data.",
        }
        self.lbl_compare_hint.setText(hints[c])

    def _apply_preset(self) -> None:
        label = self.cb_preset.currentText()
        cron = SCHEDULE_PRESETS.get(label, "")
        self.ed_cron.setText(cron)

    def _on_accept(self) -> None:
        name = self.ed_name.text().strip()
        src = self.ed_src.text().strip()
        dst = self.ed_dst.text().strip()
        cron = self.ed_cron.text().strip()

        if not name:
            QMessageBox.warning(self, "Dati mancanti", "Inserire un nome per il profilo.")
            return
        if not src or not dst:
            QMessageBox.warning(self, "Dati mancanti", "Inserire sorgente e destinazione.")
            return
        if src == dst:
            QMessageBox.warning(self, "Percorsi uguali", "Sorgente e destinazione devono essere diverse.")
            return
        if not cron_is_valid(cron):
            QMessageBox.warning(
                self,
                "Cron non valido",
                "L'espressione cron non è valida. Lasciare vuoto per disattivare la schedulazione.",
            )
            return

        # Aggiorna il profilo
        p = self.profile
        p.name = name
        p.source = src
        p.destination = dst
        p.mode = self.cb_mode.currentData()
        p.compare = self.cb_compare.currentData()
        p.verify_hash_after_copy = self.chk_verify.isChecked()
        p.max_retries = self.sp_retries.value()
        p.throttle_mb_per_sec = self.sp_throttle.value()
        p.cloud_pace_mode = self.chk_cloud.isChecked()
        p.compress = self.chk_compress.isChecked()
        p.exclude_patterns = [
            line.strip()
            for line in self.ed_excludes.toPlainText().splitlines()
            if line.strip()
        ]
        p.schedule_cron = cron
        self.accept()

    def result_profile(self) -> BackupProfile:
        return self.profile
