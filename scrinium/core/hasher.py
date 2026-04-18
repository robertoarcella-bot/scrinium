"""Calcolo hash file a blocchi (SHA-256)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

CHUNK = 1024 * 1024  # 1 MiB


def sha256_file(path: Path, cancel: Callable[[], bool] | None = None) -> str:
    """Calcola SHA-256 di un file leggendo a blocchi.

    `cancel`: callable che se restituisce True interrompe il calcolo
    (sollevando InterruptedError).
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            if cancel and cancel():
                raise InterruptedError("Hash cancellato dall'utente")
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
