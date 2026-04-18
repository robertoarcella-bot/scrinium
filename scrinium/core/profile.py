"""Modello profilo di backup e persistenza su JSON.

Ogni profilo descrive UNA operazione sorgente -> destinazione con opzioni
chiare e documentate. I profili vengono salvati in %APPDATA%/Scrinium/profiles.json.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

from scrinium.utils.paths import profiles_file

# Modalità di sincronizzazione
# - "full"        : copia TUTTO ogni volta (sovrascrive sempre)
# - "incremental" : copia solo i file nuovi o modificati nella sorgente,
#                   NON tocca i file già presenti in destinazione che non
#                   sono più nella sorgente
# - "mirror"      : come incremental, ma ELIMINA dalla destinazione i file
#                   che non esistono più nella sorgente (copia identica 1:1)
BackupMode = Literal["full", "incremental", "mirror"]

# Criterio per decidere se un file è "cambiato"
# - "size_mtime" : veloce (default) - confronta dimensione e data modifica
# - "hash"       : sicuro - confronta hash SHA-256 (più lento, I/O intenso)
CompareMode = Literal["size_mtime", "hash"]


@dataclass
class BackupProfile:
    """Profilo di backup.

    Attributi descritti in italiano per essere mostrati direttamente in GUI
    tramite le proprietà .mode_description / .compare_description.
    """

    name: str
    source: str
    destination: str
    mode: BackupMode = "incremental"
    compare: CompareMode = "size_mtime"
    verify_hash_after_copy: bool = True  # verifica hash dopo la copia
    max_retries: int = 3
    retry_backoff_sec: float = 2.0  # secondi iniziali, raddoppia ogni tentativo
    throttle_mb_per_sec: float = 0.0  # 0 = nessun limite
    exclude_patterns: list[str] = field(default_factory=list)  # glob, es. "*.tmp"
    schedule_cron: str = ""  # cron string (APScheduler), vuoto = nessuna schedulazione
    # Modalità "cloud": pausa tra un file e l'altro + attesa lunga quando
    # il disco locale è saturo, così Google Drive (o simili) ha tempo di
    # caricare la coda e liberare la cache locale prima di scrivere altro.
    cloud_pace_mode: bool = False
    cloud_pace_sleep_sec: float = 1.0  # pausa tra un file e l'altro
    cloud_enospc_wait_sec: float = 120.0  # attesa iniziale su errore "disco pieno"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    last_run: str | None = None  # ISO timestamp
    last_status: str | None = None  # "success" | "partial" | "failed"
    last_report: dict | None = None  # counters ultimo run

    @property
    def mode_description(self) -> str:
        return {
            "full": "Copia completa: sovrascrive ogni volta tutti i file.",
            "incremental": "Incrementale: copia solo i file nuovi o modificati. Non cancella nulla in destinazione.",
            "mirror": "Mirror: copia identica 1:1. Elimina in destinazione i file non più presenti in sorgente.",
        }[self.mode]

    @property
    def compare_description(self) -> str:
        return {
            "size_mtime": "Veloce: confronta dimensione e data di modifica.",
            "hash": "Sicuro: confronta hash SHA-256 (più lento).",
        }[self.compare]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BackupProfile":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)


class ProfileStore:
    """Caricamento/salvataggio lista profili su JSON."""

    def __init__(self, path=None):
        self.path = path or profiles_file()
        self.profiles: list[BackupProfile] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.profiles = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.profiles = [BackupProfile.from_dict(p) for p in data]
        except (json.JSONDecodeError, OSError):
            self.profiles = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([p.to_dict() for p in self.profiles], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def get(self, profile_id: str) -> BackupProfile | None:
        return next((p for p in self.profiles if p.id == profile_id), None)

    def upsert(self, profile: BackupProfile) -> None:
        for i, p in enumerate(self.profiles):
            if p.id == profile.id:
                self.profiles[i] = profile
                self.save()
                return
        self.profiles.append(profile)
        self.save()

    def delete(self, profile_id: str) -> None:
        self.profiles = [p for p in self.profiles if p.id != profile_id]
        self.save()

    def update_run_info(
        self, profile_id: str, status: str, report: dict
    ) -> None:
        p = self.get(profile_id)
        if not p:
            return
        p.last_run = datetime.now().isoformat(timespec="seconds")
        p.last_status = status
        p.last_report = report
        self.save()
