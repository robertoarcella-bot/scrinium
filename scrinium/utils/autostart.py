"""Avvio automatico di Scrinium all'accensione di Windows.

Scrive una voce in ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
con il percorso dell'eseguibile corrente e il flag ``--startup``.

- Livello utente (HKCU): non richiede privilegi di amministratore.
- ``--startup`` dice al programma di partire silenziosamente nella barra di
  sistema (tray) invece di mostrare subito la finestra.

Su sistemi non-Windows le funzioni sono no-op: `is_enabled()` ritorna False,
`enable()` / `disable()` ritornano False senza errori.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE_NAME = "Scrinium"
STARTUP_FLAG = "--startup"


def _executable_command() -> str:
    """Comando da registrare per l'avvio, con flag --startup.

    - Se lanciato dall'exe PyInstaller: usa sys.executable
    - In sviluppo (python -m scrinium): usa il python corrente + -m scrinium
    """
    exe = Path(sys.executable).resolve()
    if exe.name.lower() == "scrinium.exe":
        return f'"{exe}" {STARTUP_FLAG}'
    # Sviluppo: pyton + -m scrinium
    return f'"{exe}" -m scrinium {STARTUP_FLAG}'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKeyEx(
            winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ
        ) as k:
            val, _ = winreg.QueryValueEx(k, REG_VALUE_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> bool:
    """Attiva l'autostart. Ritorna True se andato a buon fine."""
    if sys.platform != "win32":
        return False
    import winreg

    cmd = _executable_command()
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.SetValueEx(k, REG_VALUE_NAME, 0, winreg.REG_SZ, cmd)
        log.info("Autostart abilitato: %s", cmd)
        return True
    except OSError:
        log.exception("Impossibile abilitare l'autostart")
        return False


def disable() -> bool:
    """Disattiva l'autostart. Ritorna True se andato a buon fine
    (anche se la chiave non era presente)."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKeyEx(
            winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.DeleteValue(k, REG_VALUE_NAME)
        log.info("Autostart disabilitato")
        return True
    except FileNotFoundError:
        return True  # già non presente
    except OSError:
        log.exception("Impossibile disabilitare l'autostart")
        return False


def is_startup_launch() -> bool:
    """True se il processo è stato lanciato con il flag --startup
    (tipicamente da Windows al boot)."""
    return STARTUP_FLAG in sys.argv
