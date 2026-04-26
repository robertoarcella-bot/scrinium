"""Preferenze applicazione persistenti su JSON.

Salvate in ``%APPDATA%/Scrinium/preferences.json`` (o equivalente per
piattaforma). Le preferenze sono distinte dai profili di backup:
qui vivono solo le opzioni globali dell'app (modalità schedulazione,
ecc.).
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from scrinium.utils.paths import app_data_dir

log = logging.getLogger(__name__)

# Modalità schedulazione:
# - "task_scheduler" : usa Windows Task Scheduler (consigliata, persistente,
#                      sveglia il PC dallo sleep, sopravvive ai crash)
# - "in_app"         : usa APScheduler dentro Scrinium (legacy, attiva solo
#                      finché l'app è aperta e sveglia)
SchedulerMode = str  # "task_scheduler" | "in_app"


def _default_scheduler_mode() -> SchedulerMode:
    return "task_scheduler" if sys.platform == "win32" else "in_app"


@dataclass
class Preferences:
    scheduler_mode: SchedulerMode = "task_scheduler"

    @classmethod
    def from_dict(cls, data: dict) -> "Preferences":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)


def _prefs_path() -> Path:
    return app_data_dir() / "preferences.json"


def load() -> Preferences:
    p = _prefs_path()
    if not p.exists():
        return Preferences(scheduler_mode=_default_scheduler_mode())
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return Preferences.from_dict(data)
    except (json.JSONDecodeError, OSError):
        log.warning("preferences.json illeggibile, uso i default", exc_info=True)
        return Preferences(scheduler_mode=_default_scheduler_mode())


def save(prefs: Preferences) -> None:
    p = _prefs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(asdict(prefs), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(p)
