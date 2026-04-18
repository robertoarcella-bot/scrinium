"""Percorsi standard dell'applicazione, cross-platform."""
import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """Cartella dati utente, secondo convenzione del sistema operativo.

    - Windows: %APPDATA%\\Scrinium
    - macOS:   ~/Library/Application Support/Scrinium
    - Linux:   $XDG_CONFIG_HOME/scrinium (default ~/.config/scrinium)
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Scrinium"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Scrinium"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "scrinium"


def profiles_file() -> Path:
    return app_data_dir() / "profiles.json"


def state_dir() -> Path:
    d = app_data_dir() / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return app_data_dir() / "scrinium.log"
