"""Finestra principale di Scrinium."""
from __future__ import annotations

import logging
from datetime import datetime

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scrinium import (
    __app_name__,
    __authors__,
    __release_date__,
    __tagline__,
    __version__,
)
from scrinium.core.engine import BackupReport
from scrinium.core.profile import BackupProfile, ProfileStore
from scrinium.core.scheduler import BackupScheduler
from scrinium.gui.profile_editor import ProfileEditor
from scrinium.gui.run_dialog import RunDialog

log = logging.getLogger(__name__)


def _fmt_dt(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def make_app_icon(size: int = 64) -> QIcon:
    """Icona generata a runtime: quadrato blu navy con 'S' bianca."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#1e3a8a"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, size // 6, size // 6)
    painter.setPen(QColor("white"))
    font = QFont("Segoe UI", int(size * 0.55), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), "S")
    painter.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__app_name__} — {__tagline__}")
        # La finestra è ridimensionabile liberamente: impostiamo solo una
        # dimensione minima, così l'utente può ingrandirla o rimpicciolirla.
        self.setMinimumSize(640, 420)
        self.resize(1000, 560)
        self.setWindowState(Qt.WindowState.WindowNoState)
        self.setWindowIcon(make_app_icon())

        self._really_quit = False
        self._tray_message_shown = False
        # Profili con run attivo (per bloccare lanci concorrenti dallo
        # scheduler mentre un RunDialog precedente è ancora aperto).
        self._running_profile_ids: set[str] = set()

        self.store = ProfileStore()
        self.scheduler = BackupScheduler(self.store, self._run_scheduled)
        self.scheduler.reload()

        self._build_ui()
        self._build_menu()
        self._setup_tray()
        self._refresh_table()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        intro = QLabel(
            f"<h2>{__app_name__}</h2>"
            f"<p>{__tagline__}. Gestisci più profili di backup, "
            f"ognuno con sorgente, destinazione e regole proprie.</p>"
        )
        layout.addWidget(intro)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Nome", "Sorgente", "Destinazione", "Modalità", "Schedulazione", "Ultimo run", "Esito"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._on_edit)
        layout.addWidget(self.table, 1)

        btns = QHBoxLayout()
        self.btn_new = QPushButton("Nuovo profilo")
        self.btn_edit = QPushButton("Modifica")
        self.btn_del = QPushButton("Elimina")
        self.btn_run = QPushButton("Esegui ora")
        btns.addWidget(self.btn_new)
        btns.addWidget(self.btn_edit)
        btns.addWidget(self.btn_del)
        btns.addStretch(1)
        btns.addWidget(self.btn_run)
        layout.addLayout(btns)

        self.btn_new.clicked.connect(self._on_new)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_del.clicked.connect(self._on_delete)
        self.btn_run.clicked.connect(self._on_run)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Pronto.")

    def _build_menu(self) -> None:
        bar = self.menuBar()
        m_file = bar.addMenu("&File")

        act_hide = QAction("Nascondi nella barra di sistema", self)
        act_hide.setShortcut("Ctrl+H")
        act_hide.triggered.connect(self._hide_to_tray)
        m_file.addAction(act_hide)

        m_file.addSeparator()

        act_quit = QAction("Esci", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self._quit_app)
        m_file.addAction(act_quit)

        m_help = bar.addMenu("&Aiuto")
        act_about = QAction("Informazioni su Scrinium...", self)
        act_about.triggered.connect(self._show_about)
        m_help.addAction(act_about)

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self) -> None:
        """Crea l'icona nella barra di sistema con menu contestuale.

        Se QSystemTrayIcon non è disponibile (ambienti molto ridotti),
        la chiusura della finestra chiude effettivamente l'applicazione.
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return

        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.setToolTip(f"{__app_name__} — {__tagline__}")

        menu = QMenu()
        self.act_tray_show = QAction("Apri Scrinium", self)
        self.act_tray_show.triggered.connect(self._show_from_tray)
        menu.addAction(self.act_tray_show)

        menu.addSeparator()

        self.menu_tray_profiles = menu.addMenu("Esegui backup")
        menu.aboutToShow.connect(self._rebuild_tray_profiles_menu)

        menu.addSeparator()

        act_quit = QAction("Esci da Scrinium", self)
        act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _rebuild_tray_profiles_menu(self) -> None:
        """Popola dinamicamente il sottomenu 'Esegui backup' con i profili."""
        self.menu_tray_profiles.clear()
        if not self.store.profiles:
            act = self.menu_tray_profiles.addAction("(nessun profilo configurato)")
            act.setEnabled(False)
            return
        for p in self.store.profiles:
            a = self.menu_tray_profiles.addAction(p.name)
            a.triggered.connect(lambda _checked, prof=p: self._run_from_tray(prof))

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _hide_to_tray(self) -> None:
        if self.tray:
            self.hide()
            if not self._tray_message_shown:
                self.tray.showMessage(
                    __app_name__,
                    "Scrinium continua a girare nella barra di sistema. "
                    "Clicca sull'icona per riaprire.",
                    make_app_icon(),
                    4000,
                )
                self._tray_message_shown = True
        else:
            self.showMinimized()

    def _run_from_tray(self, profile: BackupProfile) -> None:
        self._show_from_tray()
        self._launch_backup(profile)

    def _quit_app(self) -> None:
        ans = QMessageBox.question(
            self,
            "Uscire da Scrinium?",
            "Uscendo, le schedulazioni automatiche non saranno più eseguite "
            "finché non riapri l'applicazione.\n\nVuoi uscire davvero?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._really_quit = True
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()

    # ------------------------------------------------------------------
    # Tabella
    # ------------------------------------------------------------------

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.store.profiles))
        mode_label = {
            "full": "Completa",
            "incremental": "Incrementale",
            "mirror": "Mirror",
        }
        for row, p in enumerate(self.store.profiles):
            self.table.setItem(row, 0, QTableWidgetItem(p.name))
            self.table.setItem(row, 1, QTableWidgetItem(p.source))
            self.table.setItem(row, 2, QTableWidgetItem(p.destination))
            self.table.setItem(row, 3, QTableWidgetItem(mode_label.get(p.mode, p.mode)))
            self.table.setItem(row, 4, QTableWidgetItem(p.schedule_cron or "—"))
            self.table.setItem(row, 5, QTableWidgetItem(_fmt_dt(p.last_run)))
            status = p.last_status or "—"
            item = QTableWidgetItem(status)
            if status == "success":
                item.setForeground(Qt.GlobalColor.darkGreen)
            elif status == "partial":
                item.setForeground(Qt.GlobalColor.darkYellow)
            elif status == "failed":
                item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 6, item)
        self.table.resizeColumnsToContents()

    def _selected_profile(self) -> BackupProfile | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.store.profiles):
            return None
        return self.store.profiles[row]

    # ------------------------------------------------------------------
    # Azioni
    # ------------------------------------------------------------------

    def _on_new(self) -> None:
        dlg = ProfileEditor(None, self)
        if dlg.exec():
            self.store.upsert(dlg.result_profile())
            self.scheduler.reload()
            self._refresh_table()

    def _on_edit(self) -> None:
        p = self._selected_profile()
        if not p:
            return
        dlg = ProfileEditor(p, self)
        if dlg.exec():
            self.store.upsert(dlg.result_profile())
            self.scheduler.reload()
            self._refresh_table()

    def _on_delete(self) -> None:
        p = self._selected_profile()
        if not p:
            return
        ans = QMessageBox.question(
            self, "Eliminare profilo?", f"Eliminare il profilo '{p.name}'?\n(I file già copiati restano sul disco.)"
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.store.delete(p.id)
            self.scheduler.reload()
            self._refresh_table()

    def _on_run(self) -> None:
        p = self._selected_profile()
        if not p:
            QMessageBox.information(self, "Nessun profilo", "Selezionare un profilo dalla tabella.")
            return
        self._launch_backup(p)

    def _run_scheduled(self, p: BackupProfile) -> None:
        """Chiamato dallo scheduler quando scatta un trigger."""
        self.statusBar().showMessage(f"Backup automatico: {p.name}")
        self._launch_backup(p)

    def _launch_backup(self, p: BackupProfile) -> None:
        # Se lo stesso profilo è già in esecuzione, non aprirne un secondo
        # (evita finestre sovrapposte quando scheduler + utente coincidono).
        if p.id in self._running_profile_ids:
            log.info("Backup '%s' già in esecuzione, ignoro il nuovo trigger.", p.name)
            self.statusBar().showMessage(
                f"'{p.name}' è già in esecuzione — nuovo avvio ignorato."
            )
            return
        self._running_profile_ids.add(p.id)
        try:
            dlg = RunDialog(p, self)
            dlg.exec()
            if dlg.report is not None:
                self.store.update_run_info(p.id, dlg.report.status, dlg.report.to_dict())
                self._refresh_table()
                self.statusBar().showMessage(
                    f"'{p.name}' terminato con stato: {dlg.report.status}."
                )
        finally:
            self._running_profile_ids.discard(p.id)

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------

    def _show_about(self) -> None:
        authors_html = "<br>".join(__authors__)
        QMessageBox.about(
            self,
            f"Informazioni su {__app_name__}",
            f"""
            <h2 style="color:#1e3a8a; margin-bottom:0;">{__app_name__}
                <span style="color:#64748b; font-size:12pt;">v{__version__}</span>
            </h2>
            <p style="color:#2563eb; margin-top:4px;"><i>{__tagline__}</i></p>
            <p><b>Software libero e open source</b>, pensato per avvocati,
            giuristi e studi professionali &mdash; e più in generale per
            chiunque abbia necessità di conservare con cura e sicurezza
            i propri dati e documenti: fascicoli, contratti, scritti,
            archivi, fotografie, corrispondenza, memorie personali.</p>
            <p>Scrinium nasce dall'idea che la custodia dei propri documenti
            debba essere un gesto semplice, trasparente e verificabile,
            affidato a uno strumento di cui si possa leggere e controllare
            ogni riga di codice.</p>
            <hr>
            <p><b>Data di rilascio:</b> {__release_date__}</p>
            <p><b>Autori:</b><br>{authors_html}</p>
            """,
        )

    # ------------------------------------------------------------------
    # Chiusura
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        # Se è disponibile la tray e non stiamo davvero uscendo, nascondi
        # la finestra invece di terminare l'app (lo scheduler continua).
        if self.tray and not self._really_quit:
            event.ignore()
            self._hide_to_tray()
            return
        self.scheduler.shutdown()
        super().closeEvent(event)
