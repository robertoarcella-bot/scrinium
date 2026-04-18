"""Configurazione logging applicazione."""
import logging
from logging.handlers import RotatingFileHandler

from scrinium.utils.paths import log_file


def setup_logging(level: int = logging.INFO) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)

    # Evita duplicati se richiamato più volte
    for h in list(root.handlers):
        root.removeHandler(h)

    file_handler = RotatingFileHandler(
        log_file(), maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
