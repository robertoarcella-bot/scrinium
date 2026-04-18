"""Scheduler integrato (APScheduler) per l'esecuzione automatica dei profili.

Lo scheduler gira dentro l'applicazione: i profili con `schedule_cron`
non vuoto vengono eseguiti automaticamente agli orari indicati quando
l'app è in esecuzione (anche minimizzata in tray).

Per una schedulazione persistente anche a PC acceso ma app chiusa,
usare il Task Scheduler di Windows richiamando `scrinium.exe --run-profile <id>`.
"""
from __future__ import annotations

import logging
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from scrinium.core.profile import BackupProfile, ProfileStore

log = logging.getLogger(__name__)


class BackupScheduler:
    """Wrapper attorno a APScheduler.

    Il callback `run_fn` viene chiamato con il `BackupProfile` quando
    il trigger scatta. La GUI lo collega al motore di backup.
    """

    def __init__(
        self,
        store: ProfileStore,
        run_fn: Callable[[BackupProfile], None],
    ):
        self.store = store
        self.run_fn = run_fn
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

    def reload(self) -> None:
        """Ricarica tutti i job dai profili correnti."""
        self.scheduler.remove_all_jobs()
        for p in self.store.profiles:
            if p.schedule_cron.strip():
                try:
                    trigger = CronTrigger.from_crontab(p.schedule_cron.strip())
                    self.scheduler.add_job(
                        self._fire,
                        trigger=trigger,
                        args=[p.id],
                        id=p.id,
                        replace_existing=True,
                        misfire_grace_time=3600,
                        # Se il job precedente per lo stesso profilo è ancora
                        # in esecuzione, APScheduler salta l'esecuzione
                        # corrente invece di avviare un secondo run parallelo.
                        max_instances=1,
                        coalesce=True,
                    )
                    log.info("Schedulato profilo '%s': %s", p.name, p.schedule_cron)
                except Exception as e:
                    log.error("Cron invalido per '%s' (%s): %s", p.name, p.schedule_cron, e)

    def _fire(self, profile_id: str) -> None:
        # Ricarica il profilo dal disco: potrebbe essere cambiato
        self.store.load()
        profile = self.store.get(profile_id)
        if not profile:
            log.warning("Profilo %s non trovato allo scatto del trigger", profile_id)
            return
        log.info("Trigger scattato per profilo '%s'", profile.name)
        try:
            self.run_fn(profile)
        except Exception:
            log.exception("Errore esecuzione schedulata profilo %s", profile.name)

    def next_run_time(self, profile_id: str):
        job = self.scheduler.get_job(profile_id)
        return job.next_run_time if job else None

    def shutdown(self) -> None:
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helper: conversione tra "preset amichevole" <-> cron
# ---------------------------------------------------------------------------

SCHEDULE_PRESETS = {
    "nessuna": "",
    "ogni ora": "0 * * * *",
    "ogni giorno alle 22:00": "0 22 * * *",
    "ogni giorno alle 03:00": "0 3 * * *",
    "ogni lunedì alle 08:00": "0 8 * * 1",
    "ogni 1° del mese alle 02:00": "0 2 1 * *",
}


def cron_is_valid(expr: str) -> bool:
    if not expr.strip():
        return True
    try:
        CronTrigger.from_crontab(expr.strip())
        return True
    except Exception:
        return False
