"""Motore di backup.

Implementa:
- scansione sorgente/destinazione
- decisione file da copiare (full / incremental / mirror)
- copia con throttling I/O
- verifica hash post-copia
- retry automatico con backoff esponenziale
- callback di progresso (compatibile con GUI via signal)
- cancellazione cooperativa (pausa/stop)
"""
from __future__ import annotations

import fnmatch
import logging
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from scrinium.core.hasher import sha256_file
from scrinium.core.profile import BackupProfile

log = logging.getLogger(__name__)

CHUNK = 1024 * 1024  # 1 MiB

# Minima frequenza di emissione dei progress signal verso la GUI (secondi).
# A ~10 Hz la UI resta fluida anche con 100k+ file.
PROGRESS_MIN_INTERVAL = 0.1

# File sempre esclusi, indipendentemente dai pattern utente.
# desktop.ini e Thumbs.db: metadati Windows, spesso protetti/proibiti
# ~$*: file di lock temporanei di Microsoft Office
# .DS_Store: metadati Finder su macOS
# *.scrinium-part: file temporanei generati da Scrinium durante la copia
_BUILTIN_EXCLUDES = (
    "desktop.ini",
    "Thumbs.db",
    "~$*",
    ".DS_Store",
    "*.scrinium-part",
)


def _win_long(path) -> str:
    """Restituisce il percorso in forma utilizzabile anche oltre MAX_PATH (260).

    Su Windows antepone il prefisso ``\\\\?\\`` (o ``\\\\?\\UNC\\`` per percorsi
    di rete), che bypassa il limite storico di 260 caratteri delle Win32 API.
    Richiede percorsi assoluti e normalizzati. Su altre piattaforme
    restituisce semplicemente ``str(path)``.
    """
    s = str(path)
    if sys.platform != "win32":
        return s
    if s.startswith("\\\\?\\"):
        return s
    abs_s = os.path.abspath(s)
    if abs_s.startswith("\\\\"):
        # UNC path \\server\share\... -> \\?\UNC\server\share\...
        return "\\\\?\\UNC\\" + abs_s[2:]
    return "\\\\?\\" + abs_s

# ---------------------------------------------------------------------------
# Tipi di supporto
# ---------------------------------------------------------------------------


@dataclass
class Progress:
    """Snapshot dello stato di avanzamento (passato alle callback GUI)."""

    phase: str = ""  # "scan" | "copy" | "verify" | "cleanup" | "done"
    current_file: str = ""
    files_total: int = 0
    files_done: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    errors: int = 0
    message: str = ""


@dataclass
class BackupReport:
    started_at: float = 0.0
    ended_at: float = 0.0
    files_copied: int = 0
    files_updated: int = 0
    files_skipped: int = 0
    files_deleted: int = 0
    files_failed: int = 0
    bytes_copied: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (path, error)
    was_interrupted: bool = False  # True se stop richiesto dall'utente

    @property
    def status(self) -> str:
        if self.was_interrupted:
            return "interrupted"
        if self.files_failed == 0:
            return "success"
        if self.files_copied + self.files_updated > 0:
            return "partial"
        return "failed"

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.ended_at - self.started_at)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_sec": round(self.duration_sec, 2),
            "files_copied": self.files_copied,
            "files_updated": self.files_updated,
            "files_skipped": self.files_skipped,
            "files_deleted": self.files_deleted,
            "files_failed": self.files_failed,
            "bytes_copied": self.bytes_copied,
            "failures": self.failures[:50],  # non esplodere il JSON
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Controllo di esecuzione (pausa/stop)
# ---------------------------------------------------------------------------


class RunControl:
    """Oggetto condiviso per controllo di esecuzione.

    Permette a GUI/scheduler di chiedere pause, riprese o interruzioni
    in modo cooperativo (il motore verifica periodicamente).
    """

    def __init__(self) -> None:
        self._pause = threading.Event()
        self._stop = threading.Event()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def stop(self) -> None:
        self._stop.set()

    @property
    def should_stop(self) -> bool:
        return self._stop.is_set()

    def wait_if_paused(self) -> None:
        while self._pause.is_set() and not self._stop.is_set():
            time.sleep(0.2)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _is_excluded(rel_path: str, patterns: list[str]) -> bool:
    """Ritorna True se il file va escluso.

    Combina i pattern dell'utente con quelli built-in (sempre attivi).
    """
    parts = rel_path.replace("\\", "/").split("/")
    all_patterns = list(patterns) + list(_BUILTIN_EXCLUDES)
    for pat in all_patterns:
        for p in parts:
            if fnmatch.fnmatch(p, pat):
                return True
        if fnmatch.fnmatch(rel_path, pat):
            return True
    return False


def _files_differ_size_mtime(src: Path, dst: Path) -> bool:
    try:
        s = os.stat(_win_long(src))
        d = os.stat(_win_long(dst))
    except OSError:
        return True
    if s.st_size != d.st_size:
        return True
    # Tolleranza 2s per FAT32 / differenze FS
    if abs(s.st_mtime - d.st_mtime) > 2:
        return True
    return False


def _scan_source(
    source: Path,
    exclude: list[str],
    control: RunControl,
    on_progress: Callable[[Progress], None] | None,
) -> list[tuple[Path, str, int]]:
    """Ritorna lista di (src_abs, rel_path, size)."""
    out: list[tuple[Path, str, int]] = []
    prog = Progress(phase="scan", message="Scansione sorgente in corso...")
    for root, dirs, files in os.walk(source):
        if control.should_stop:
            break
        root_path = Path(root)
        # Exclusione directory (applica sui nomi singoli)
        dirs[:] = [d for d in dirs if not _is_excluded(d, exclude)]
        for f in files:
            if control.should_stop:
                break
            src = root_path / f
            try:
                rel = str(src.relative_to(source))
            except ValueError:
                continue
            if _is_excluded(rel, exclude):
                continue
            try:
                size = src.stat().st_size
            except OSError:
                size = 0
            out.append((src, rel, size))
            if len(out) % 500 == 0 and on_progress:
                prog.files_total = len(out)
                prog.message = f"Scansione... {len(out)} file trovati"
                on_progress(prog)
    return out


def _scan_destination(destination: Path) -> set[str]:
    """Ritorna insieme di rel_path presenti in destinazione."""
    out: set[str] = set()
    if not destination.exists():
        return out
    for root, _dirs, files in os.walk(destination):
        root_path = Path(root)
        for f in files:
            try:
                rel = str((root_path / f).relative_to(destination))
                out.add(rel)
            except ValueError:
                continue
    return out


def _copy_with_throttle(
    src: Path,
    dst: Path,
    throttle_mb_s: float,
    control: RunControl,
    on_bytes: Callable[[int], None] | None = None,
) -> None:
    """Copia a blocchi con throttling opzionale.

    Se throttle_mb_s <= 0, nessun limite.
    """
    # Usa sempre percorsi con prefisso \\?\ su Windows per evitare
    # il limite MAX_PATH (260 caratteri) sui path profondi/lunghi.
    src_s = _win_long(src)
    dst_s = _win_long(dst)
    os.makedirs(_win_long(dst.parent), exist_ok=True)
    bytes_per_sec = int(throttle_mb_s * 1024 * 1024) if throttle_mb_s > 0 else 0
    written_in_window = 0
    window_start = time.monotonic()

    tmp = dst.with_suffix(dst.suffix + ".scrinium-part")
    tmp_s = _win_long(tmp)
    try:
        with open(src_s, "rb") as fi, open(tmp_s, "wb") as fo:
            while True:
                if control.should_stop:
                    raise InterruptedError("Backup interrotto dall'utente")
                control.wait_if_paused()
                chunk = fi.read(CHUNK)
                if not chunk:
                    break
                fo.write(chunk)
                if on_bytes:
                    on_bytes(len(chunk))
                if bytes_per_sec > 0:
                    written_in_window += len(chunk)
                    elapsed = time.monotonic() - window_start
                    expected = written_in_window / bytes_per_sec
                    if expected > elapsed:
                        time.sleep(expected - elapsed)
                    if elapsed > 1.0:
                        written_in_window = 0
                        window_start = time.monotonic()
        # Preserva metadati (mtime, permessi)
        shutil.copystat(src_s, tmp_s)
        os.replace(tmp_s, dst_s)
    except Exception:
        # Rimuovi file temporaneo in caso di errore
        try:
            if os.path.exists(tmp_s):
                os.remove(tmp_s)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Motore principale
# ---------------------------------------------------------------------------


class BackupEngine:
    """Esegue un backup secondo un profilo."""

    def __init__(
        self,
        profile: BackupProfile,
        on_progress: Callable[[Progress], None] | None = None,
        control: RunControl | None = None,
    ):
        self.profile = profile
        self.on_progress = on_progress
        self.control = control or RunControl()
        self.report = BackupReport()
        self._last_emit_at: float = 0.0
        self._last_checkpoint_at: float = 0.0

    # -- API pubblica -------------------------------------------------------

    def run(self) -> BackupReport:
        p = self.profile
        src = Path(p.source)
        dst = Path(p.destination)

        self.report.started_at = time.time()
        self._last_checkpoint_at = time.monotonic()
        log.info("[%s] START %s -> %s mode=%s", p.name, src, dst, p.mode)

        try:
            if not src.exists() or not src.is_dir():
                msg = f"Sorgente non trovata o non è una cartella: {src}"
                log.error(msg)
                self.report.failures.append((str(src), msg))
                self.report.files_failed = 1
                return self.report

            try:
                os.makedirs(_win_long(dst), exist_ok=True)
            except OSError as e:
                msg = f"Impossibile creare destinazione: {e}"
                log.error(msg)
                self.report.failures.append((str(dst), msg))
                self.report.files_failed = 1
                return self.report

            # 1) Scan sorgente
            items = _scan_source(src, p.exclude_patterns, self.control, self.on_progress)
            total_bytes = sum(s for _, _, s in items)

            prog = Progress(
                phase="copy",
                files_total=len(items),
                bytes_total=total_bytes,
                message="Avvio copia...",
            )
            self._emit(prog, force=True)

            # 2) Copia
            for src_path, rel, size in items:
                if self.control.should_stop:
                    break
                self.control.wait_if_paused()

                dst_path = dst / rel
                prog.current_file = rel
                prog.message = f"Copia: {rel}"
                self._emit(prog)

                try:
                    action = self._decide_action(src_path, dst_path)
                    if action == "skip":
                        self.report.files_skipped += 1
                    else:
                        self._copy_with_retries(src_path, dst_path, p, prog)
                        if action == "copy":
                            self.report.files_copied += 1
                        else:
                            self.report.files_updated += 1
                        self.report.bytes_copied += size
                except InterruptedError:
                    log.warning("Backup interrotto durante la copia di %s", rel)
                    break
                except Exception as e:
                    log.exception("Errore copia %s", rel)
                    self.report.files_failed += 1
                    self.report.failures.append((rel, str(e)))
                    prog.errors += 1
                    # Gli errori sono sempre importanti, la GUI deve vederli
                    self._emit(prog, force=True)

                prog.files_done += 1
                prog.bytes_done += size
                self._emit(prog)

                # Checkpoint: ogni ~30s scrive una copia corrente del log,
                # così anche in caso di kill brutale (taskkill /F) resta un
                # report parziale leggibile nella destinazione.
                self._maybe_checkpoint(dst)

            # 3) Mirror: rimuovi file in destinazione non più in sorgente
            if p.mode == "mirror" and not self.control.should_stop:
                self._mirror_cleanup(src, dst, items, prog)

            # 4) Fine
            prog.phase = "done"
            prog.message = (
                f"Completato. Copiati {self.report.files_copied}, "
                f"aggiornati {self.report.files_updated}, "
                f"saltati {self.report.files_skipped}, "
                f"falliti {self.report.files_failed}."
            )
            self._emit(prog, force=True)

            return self.report
        finally:
            # Aggiorna sempre il report ed il log in destinazione, anche
            # se il run è stato interrotto (stop cooperativo) o se è stata
            # sollevata un'eccezione non gestita a monte.
            if self.report.ended_at == 0.0:
                self.report.ended_at = time.time()
            if self.control.should_stop:
                self.report.was_interrupted = True
            log.info(
                "[%s] END status=%s copiati=%s aggiornati=%s saltati=%s falliti=%s",
                p.name,
                self.report.status,
                self.report.files_copied,
                self.report.files_updated,
                self.report.files_skipped,
                self.report.files_failed,
            )
            try:
                self._write_destination_log(dst, final=True)
            except Exception:
                log.exception("Errore scrittura log finale in destinazione")

    # -- Logica interna -----------------------------------------------------

    def _decide_action(self, src: Path, dst: Path) -> str:
        """Ritorna 'copy' | 'update' | 'skip'."""
        p = self.profile
        if p.mode == "full":
            return "copy" if not dst.exists() else "update"

        if not dst.exists():
            return "copy"

        # incremental / mirror: confronta
        if p.compare == "size_mtime":
            if _files_differ_size_mtime(src, dst):
                return "update"
            return "skip"
        # hash
        try:
            s_hash = sha256_file(src, lambda: self.control.should_stop)
            d_hash = sha256_file(dst, lambda: self.control.should_stop)
        except InterruptedError:
            raise
        except OSError:
            return "update"
        return "skip" if s_hash == d_hash else "update"

    def _copy_with_retries(
        self, src: Path, dst: Path, profile: BackupProfile, prog: Progress
    ) -> None:
        """Copia con retry + verifica hash post-copia se abilitata."""
        last_err: Exception | None = None
        backoff = profile.retry_backoff_sec

        for attempt in range(1, profile.max_retries + 1):
            if self.control.should_stop:
                raise InterruptedError("Stop richiesto")
            try:
                _copy_with_throttle(
                    src,
                    dst,
                    profile.throttle_mb_per_sec,
                    self.control,
                )
                if profile.verify_hash_after_copy:
                    prog.message = f"Verifica: {dst.name}"
                    self._emit(prog)
                    s_hash = sha256_file(src, lambda: self.control.should_stop)
                    d_hash = sha256_file(dst, lambda: self.control.should_stop)
                    if s_hash != d_hash:
                        raise IOError(
                            f"Verifica hash fallita (src={s_hash[:8]} dst={d_hash[:8]})"
                        )
                return  # OK
            except InterruptedError:
                raise
            except Exception as e:
                last_err = e
                log.warning(
                    "Tentativo %d/%d fallito per %s: %s",
                    attempt,
                    profile.max_retries,
                    src,
                    e,
                )
                if attempt < profile.max_retries:
                    # Pausa con backoff, cancellabile
                    slept = 0.0
                    while slept < backoff and not self.control.should_stop:
                        time.sleep(0.2)
                        slept += 0.2
                    backoff *= 2
        if last_err:
            raise last_err

    def _mirror_cleanup(
        self,
        source: Path,
        destination: Path,
        src_items: list[tuple[Path, str, int]],
        prog: Progress,
    ) -> None:
        prog.phase = "cleanup"
        prog.message = "Rimozione file obsoleti in destinazione..."
        self._emit(prog, force=True)

        src_set = {rel for _, rel, _ in src_items}
        dst_set = _scan_destination(destination)
        to_delete = dst_set - src_set
        # Non rimuovere mai i file di log scritti da Scrinium nella destinazione
        to_delete.discard("scrinium-backup.log.txt")
        to_delete.discard("scrinium-backup.in-corso.log.txt")
        to_delete.discard("scrinium-backup.in-corso.log.txt.tmp")

        for rel in to_delete:
            if self.control.should_stop:
                break
            path = destination / rel
            try:
                os.remove(_win_long(path))
                self.report.files_deleted += 1
            except OSError as e:
                log.warning("Impossibile eliminare %s: %s", path, e)

        # Rimuovi directory vuote dal basso verso l'alto
        for root, dirs, files in os.walk(destination, topdown=False):
            if self.control.should_stop:
                break
            if not dirs and not files and Path(root) != destination:
                try:
                    os.rmdir(root)
                except OSError:
                    pass

    def _emit(self, prog: Progress, force: bool = False) -> None:
        """Invia un progress alla GUI limitando la frequenza.

        Con 100k+ file, emettere su ogni file saturerebbe la UI (freeze).
        Quindi i progress "ordinari" vengono throttled a ~10 Hz; i momenti
        salienti (cambio fase, errori, inizio/fine) passano `force=True`
        per essere sempre consegnati.
        """
        if not self.on_progress:
            return
        now = time.monotonic()
        if not force and (now - self._last_emit_at) < PROGRESS_MIN_INTERVAL:
            return
        self._last_emit_at = now
        try:
            self.on_progress(prog)
        except Exception:
            log.exception("Errore callback progresso")

    def _maybe_checkpoint(self, destination: Path) -> None:
        """Scrive un checkpoint se sono passati almeno 30 secondi.

        Il checkpoint è un report parziale scritto in
        `scrinium-backup.in-corso.log.txt` (file separato, sovrascritto ogni
        volta). Serve a garantire che anche in caso di terminazione brutale
        (taskkill /F, crash di sistema, interruzione di corrente) resti
        traccia dell'avanzamento nella cartella di destinazione.
        """
        now = time.monotonic()
        if (now - self._last_checkpoint_at) < 30.0:
            return
        self._last_checkpoint_at = now
        try:
            self._write_destination_log(destination, final=False)
        except Exception:
            log.exception("Errore scrittura checkpoint")

    def _write_destination_log(self, destination: Path, final: bool = True) -> None:
        """Scrive un report leggibile .txt nella cartella di destinazione.

        Se ``final=True`` aggiorna in append ``scrinium-backup.log.txt`` (lo
        storico di tutti i run completati) e rimuove l'eventuale checkpoint
        di run in corso.

        Se ``final=False`` sovrascrive ``scrinium-backup.in-corso.log.txt``
        con una fotografia del run corrente (checkpoint periodico).

        Il fallimento della scrittura del log non pregiudica l'esito del
        backup.
        """
        try:
            p = self.profile
            r = self.report

            def _ts(epoch: float) -> str:
                if not epoch:
                    return "—"
                from datetime import datetime as _dt
                return _dt.fromtimestamp(epoch).strftime("%d/%m/%Y %H:%M:%S")

            def _mb(n: int) -> str:
                return f"{n / (1024*1024):.2f} MB" if n else "0 MB"

            mode_label = {
                "full": "Copia completa",
                "incremental": "Incrementale",
                "mirror": "Mirror (1:1)",
            }.get(p.mode, p.mode)

            compare_label = {
                "size_mtime": "dimensione + data",
                "hash": "hash SHA-256",
            }.get(p.compare, p.compare)

            if not final:
                status_label = "IN CORSO"
                title = "SCRINIUM — Report di backup (IN CORSO)"
            else:
                status_label = {
                    "success": "SUCCESSO",
                    "partial": "PARZIALE (alcuni file non copiati)",
                    "failed": "FALLITO",
                    "interrupted": "INTERROTTO DALL'UTENTE",
                }.get(r.status, r.status.upper())
                title = "SCRINIUM — Report di backup"

            ended_display = _ts(r.ended_at) if final else "— (in corso)"
            duration_display = (
                f"{r.duration_sec:.1f} s" if final else f"{max(0.0, time.time() - r.started_at):.1f} s (parziale)"
            )

            lines = [
                "=" * 72,
                title,
                "=" * 72,
                f"Profilo              : {p.name}",
                f"Modalità             : {mode_label}",
                f"Criterio di confronto: {compare_label}",
                f"Verifica hash copia  : {'sì' if p.verify_hash_after_copy else 'no'}",
                f"Sorgente             : {p.source}",
                f"Destinazione         : {p.destination}",
                "",
                f"Avvio                : {_ts(r.started_at)}",
                f"Fine                 : {ended_display}",
                f"Durata               : {duration_display}",
                "",
                f"RISULTATO            : {status_label}",
                "",
                f"File copiati         : {r.files_copied}",
                f"File aggiornati      : {r.files_updated}",
                f"File saltati         : {r.files_skipped}",
                f"File eliminati       : {r.files_deleted}",
                f"File falliti         : {r.files_failed}",
                f"Byte copiati         : {_mb(r.bytes_copied)}",
            ]
            if r.failures:
                lines.append("")
                max_failures = 20 if final else 10
                lines.append(f"Fallimenti (primi {max_failures}):")
                for path, err in r.failures[:max_failures]:
                    lines.append(f"  - {path}: {err}")
            lines.append("")

            os.makedirs(_win_long(destination), exist_ok=True)
            if final:
                log_path = destination / "scrinium-backup.log.txt"
                with open(_win_long(log_path), "a", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                    f.write("\n")
                # Pulizia del checkpoint se presente
                in_progress = destination / "scrinium-backup.in-corso.log.txt"
                try:
                    os.remove(_win_long(in_progress))
                except OSError:
                    pass
            else:
                in_progress = destination / "scrinium-backup.in-corso.log.txt"
                # Scrittura atomica: tmp + rename, così il file non è mai
                # visto troncato in caso di kill proprio durante la write.
                tmp = destination / "scrinium-backup.in-corso.log.txt.tmp"
                with open(_win_long(tmp), "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                    f.write("\n")
                os.replace(_win_long(tmp), _win_long(in_progress))
        except Exception:
            log.exception("Impossibile scrivere il log in destinazione")
