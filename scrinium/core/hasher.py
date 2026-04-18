"""Calcolo hash file a blocchi (SHA-256)."""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Callable

CHUNK = 1024 * 1024  # 1 MiB


def _win_long(path) -> str:
    """Antepone il prefisso ``\\\\?\\`` su Windows per superare MAX_PATH."""
    s = str(path)
    if sys.platform != "win32":
        return s
    if s.startswith("\\\\?\\"):
        return s
    abs_s = os.path.abspath(s)
    if abs_s.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_s[2:]
    return "\\\\?\\" + abs_s


def sha256_file(path: Path, cancel: Callable[[], bool] | None = None) -> str:
    """Calcola SHA-256 di un file leggendo a blocchi.

    `cancel`: callable che se restituisce True interrompe il calcolo
    (sollevando InterruptedError).
    """
    h = hashlib.sha256()
    with open(_win_long(path), "rb") as f:
        while True:
            if cancel and cancel():
                raise InterruptedError("Hash cancellato dall'utente")
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
