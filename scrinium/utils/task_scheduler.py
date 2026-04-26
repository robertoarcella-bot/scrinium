"""Schedulazione persistente via Windows Task Scheduler.

A differenza di APScheduler (che vive dentro Scrinium e si ferma quando
l'app è chiusa o congelata), il Task Scheduler di Windows:

- sveglia il PC dallo sleep all'ora del trigger (``WakeToRun``);
- esegue il backup anche se Scrinium non è aperto;
- recupera l'esecuzione mancata se la macchina era spenta
  (``StartWhenAvailable``).

Per ogni profilo con ``schedule_cron`` non vuoto, registriamo una task
``\\Scrinium\\<profile_id>`` che lancia ``Scrinium.exe --run-profile <id>``
all'orario indicato. Il sync è idempotente.

Il parser cron è volutamente limitato ai pattern realmente esprimibili
come CalendarTrigger nativo del Task Scheduler:

- ``M H * * *``        — ogni giorno alle H:M
- ``M H * * D``        — ogni settimana il giorno D alle H:M
- ``M H D * *``        — ogni mese il giorno D alle H:M
- ``0 * * * *``        — all'inizio di ogni ora

I pattern non riconosciuti restituiscono ``None`` da
:func:`cron_to_trigger_xml` e il chiamante può ricadere sullo scheduler
in-app per quel profilo.
"""
from __future__ import annotations

import getpass
import logging
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

TASK_FOLDER = "Scrinium"
TASK_NAME_PREFIX = f"\\{TASK_FOLDER}\\"

_DAY_NAMES = {
    0: "SUN", 1: "MON", 2: "TUE", 3: "WED",
    4: "THU", 5: "FRI", 6: "SAT", 7: "SUN",
}


def is_supported() -> bool:
    """True solo su Windows (l'unica piattaforma con Task Scheduler)."""
    return sys.platform == "win32"


# ---------------------------------------------------------------------------
# Conversione cron -> XML CalendarTrigger
# ---------------------------------------------------------------------------

@dataclass
class _Trigger:
    """Descrizione interna di un trigger calendario."""
    minute: int
    hour: int
    kind: str  # "daily" | "weekly" | "monthly" | "hourly"
    day_of_week: int | None = None   # 0-6 (lun-dom) per weekly
    day_of_month: int | None = None  # 1-31 per monthly


def parse_cron(expr: str) -> _Trigger | None:
    """Tenta di mappare un'espressione cron sui trigger nativi del Task
    Scheduler. Restituisce ``None`` se il pattern non è esprimibile come
    CalendarTrigger semplice (in tal caso il chiamante può ricadere su
    APScheduler per quel profilo)."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts

    # Caso speciale "ogni ora al minuto M": "M * * * *"
    if (
        hour == "*"
        and dom == "*"
        and month == "*"
        and dow == "*"
        and _is_int(minute)
    ):
        return _Trigger(minute=int(minute), hour=0, kind="hourly")

    # Tutti gli altri richiedono minute e hour numerici fissi.
    if not (_is_int(minute) and _is_int(hour)):
        return None
    if month != "*":
        return None  # cron mensile-specifico non supportato

    m, h = int(minute), int(hour)

    # Daily: M H * * *
    if dom == "*" and dow == "*":
        return _Trigger(minute=m, hour=h, kind="daily")

    # Weekly: M H * * D  (D singolo, 0-7)
    if dom == "*" and _is_int(dow):
        d = int(dow)
        if 0 <= d <= 7:
            # cron usa 0=dom, APScheduler usa 0=lun: noi seguiamo cron
            # (0 e 7 = domenica). Mappiamo su nomi inglesi del Task Sch.
            return _Trigger(
                minute=m, hour=h, kind="weekly", day_of_week=d
            )

    # Monthly: M H D * *  (D singolo, 1-31)
    if dow == "*" and _is_int(dom):
        d = int(dom)
        if 1 <= d <= 31:
            return _Trigger(
                minute=m, hour=h, kind="monthly", day_of_month=d
            )

    return None


def _is_int(s: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", s))


def cron_to_trigger_xml(expr: str, start_year: int) -> str | None:
    """Genera il frammento ``<Triggers>...</Triggers>`` per la task XML.

    Restituisce ``None`` se il cron non è esprimibile come trigger
    nativo del Task Scheduler.
    """
    t = parse_cron(expr)
    if t is None:
        return None

    # StartBoundary: serve solo l'orario; la data deve essere "vecchia"
    # così il trigger è già attivo. Usiamo 1° gennaio dell'anno corrente.
    start = f"{start_year}-01-01T{t.hour:02d}:{t.minute:02d}:00"

    if t.kind == "daily":
        body = (
            f"<StartBoundary>{start}</StartBoundary>"
            "<Enabled>true</Enabled>"
            "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
        )
    elif t.kind == "weekly":
        day = _DAY_NAMES[t.day_of_week or 0]
        body = (
            f"<StartBoundary>{start}</StartBoundary>"
            "<Enabled>true</Enabled>"
            "<ScheduleByWeek>"
            f"<DaysOfWeek><{day} /></DaysOfWeek>"
            "<WeeksInterval>1</WeeksInterval>"
            "</ScheduleByWeek>"
        )
    elif t.kind == "monthly":
        body = (
            f"<StartBoundary>{start}</StartBoundary>"
            "<Enabled>true</Enabled>"
            "<ScheduleByMonth>"
            f"<DaysOfMonth><Day>{t.day_of_month}</Day></DaysOfMonth>"
            "<Months>"
            "<January /><February /><March /><April /><May /><June />"
            "<July /><August /><September /><October /><November /><December />"
            "</Months>"
            "</ScheduleByMonth>"
        )
    elif t.kind == "hourly":
        # CalendarTrigger giornaliero che parte all'ora 00:M e si ripete
        # ogni ora per 24 ore. PT1H = 1 ora; PT24H = durata totale.
        start = f"{start_year}-01-01T00:{t.minute:02d}:00"
        body = (
            f"<StartBoundary>{start}</StartBoundary>"
            "<Enabled>true</Enabled>"
            "<Repetition>"
            "<Interval>PT1H</Interval>"
            "<Duration>P1D</Duration>"
            "<StopAtDurationEnd>false</StopAtDurationEnd>"
            "</Repetition>"
            "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
        )
    else:
        return None

    return f"<Triggers><CalendarTrigger>{body}</CalendarTrigger></Triggers>"


# ---------------------------------------------------------------------------
# Generazione XML completo della task
# ---------------------------------------------------------------------------

def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def build_task_xml(
    profile_name: str,
    profile_id: str,
    cron: str,
    exe_path: str,
    arguments: str,
    working_dir: str | None = None,
) -> str | None:
    """Costruisce il documento XML completo per ``schtasks /Create /XML``.

    Restituisce ``None`` se il cron non è esprimibile come trigger nativo.
    """
    triggers_xml = cron_to_trigger_xml(cron, datetime.now().year)
    if triggers_xml is None:
        return None

    user_id = _xml_escape(getpass.getuser())
    desc = _xml_escape(
        f"Backup automatico Scrinium — profilo «{profile_name}» (id={profile_id})"
    )
    cmd = _xml_escape(exe_path)
    args = _xml_escape(arguments)
    wd_xml = (
        f"<WorkingDirectory>{_xml_escape(working_dir)}</WorkingDirectory>"
        if working_dir
        else ""
    )

    # NOTE: WakeToRun=true sveglia il PC dallo sleep, StartWhenAvailable=true
    # recupera la run se la macchina era spenta all'orario previsto.
    # IgnoreNew evita esecuzioni concorrenti del medesimo profilo.
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.4" '
        'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        "<RegistrationInfo>"
        "<Author>Scrinium</Author>"
        f"<Description>{desc}</Description>"
        "</RegistrationInfo>"
        f"{triggers_xml}"
        '<Principals>'
        '<Principal id="Author">'
        f"<UserId>{user_id}</UserId>"
        "<LogonType>InteractiveToken</LogonType>"
        "<RunLevel>LeastPrivilege</RunLevel>"
        "</Principal>"
        "</Principals>"
        "<Settings>"
        "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
        "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
        "<AllowHardTerminate>true</AllowHardTerminate>"
        "<StartWhenAvailable>true</StartWhenAvailable>"
        "<RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>"
        "<IdleSettings>"
        "<StopOnIdleEnd>false</StopOnIdleEnd>"
        "<RestartOnIdle>false</RestartOnIdle>"
        "</IdleSettings>"
        "<AllowStartOnDemand>true</AllowStartOnDemand>"
        "<Enabled>true</Enabled>"
        "<Hidden>false</Hidden>"
        "<RunOnlyIfIdle>false</RunOnlyIfIdle>"
        "<WakeToRun>true</WakeToRun>"
        "<ExecutionTimeLimit>PT24H</ExecutionTimeLimit>"
        "<Priority>7</Priority>"
        "</Settings>"
        '<Actions Context="Author">'
        "<Exec>"
        f"<Command>{cmd}</Command>"
        f"<Arguments>{args}</Arguments>"
        f"{wd_xml}"
        "</Exec>"
        "</Actions>"
        "</Task>"
    )


# ---------------------------------------------------------------------------
# Wrapper su schtasks.exe
# ---------------------------------------------------------------------------

def _run_schtasks(args: list[str]) -> tuple[int, str, str]:
    """Esegue ``schtasks.exe`` senza far apparire una finestra console.

    Restituisce (returncode, stdout, stderr). stdout/stderr sono decodificati
    con la codepage Windows (mbcs) perché schtasks emette in OEM.
    """
    creationflags = 0
    if sys.platform == "win32":
        # CREATE_NO_WINDOW = 0x08000000 — evita il flash di console
        # quando Scrinium gira in modalità windowed.
        creationflags = 0x08000000
    try:
        proc = subprocess.run(
            ["schtasks.exe", *args],
            capture_output=True,
            creationflags=creationflags,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", "schtasks.exe non trovato"
    out = _decode(proc.stdout)
    err = _decode(proc.stderr)
    return proc.returncode, out, err


def _decode(b: bytes) -> str:
    for enc in ("mbcs", "cp1252", "utf-8", "latin-1"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", errors="replace")


def _task_name(profile_id: str) -> str:
    return f"{TASK_NAME_PREFIX}{profile_id}"


def task_exists(profile_id: str) -> bool:
    if not is_supported():
        return False
    rc, _, _ = _run_schtasks(["/Query", "/TN", _task_name(profile_id)])
    return rc == 0


def list_managed_task_ids() -> list[str]:
    """Elenco degli id profilo che hanno una task registrata in
    ``\\Scrinium\\``."""
    if not is_supported():
        return []
    rc, out, _ = _run_schtasks(["/Query", "/FO", "CSV", "/NH"])
    if rc != 0:
        return []
    ids = []
    for line in out.splitlines():
        # Ogni riga CSV: "TaskPath","Next Run Time","Status"
        line = line.strip()
        if not line:
            continue
        # estrai il primo campo
        m = re.match(r'"([^"]+)"', line)
        if not m:
            continue
        path = m.group(1)
        if path.startswith(TASK_NAME_PREFIX):
            ids.append(path[len(TASK_NAME_PREFIX):])
    return ids


def register_task(
    profile_name: str,
    profile_id: str,
    cron: str,
    exe_path: str,
    arguments: str,
    working_dir: str | None = None,
) -> tuple[bool, str]:
    """Crea o sostituisce la task per il profilo. Ritorna (ok, messaggio)."""
    if not is_supported():
        return False, "Task Scheduler disponibile solo su Windows"

    xml = build_task_xml(
        profile_name=profile_name,
        profile_id=profile_id,
        cron=cron,
        exe_path=exe_path,
        arguments=arguments,
        working_dir=working_dir,
    )
    if xml is None:
        return False, (
            "Espressione cron non esprimibile come trigger del Task Scheduler. "
            "Sono supportati: «M H * * *» (giornaliero), «M H * * D» "
            "(settimanale), «M H D * *» (mensile), «M * * * *» (orario)."
        )

    # schtasks /XML pretende UTF-16 LE con BOM.
    fd, tmp_path = tempfile.mkstemp(suffix=".xml", prefix="scrinium_task_")
    os.close(fd)
    try:
        Path(tmp_path).write_text(xml, encoding="utf-16")
        rc, out, err = _run_schtasks(
            [
                "/Create",
                "/TN", _task_name(profile_id),
                "/XML", tmp_path,
                "/F",  # overwrite
            ]
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if rc == 0:
        log.info(
            "Task Scheduler: registrata task per profilo '%s' (cron=%s)",
            profile_name, cron,
        )
        return True, "ok"
    msg = (err or out or f"schtasks rc={rc}").strip()
    log.warning(
        "Task Scheduler: registrazione fallita per '%s' (rc=%d): %s",
        profile_name, rc, msg,
    )
    return False, msg


def unregister_task(profile_id: str) -> bool:
    """Elimina la task associata al profilo. Ritorna True anche se la task
    non esisteva."""
    if not is_supported():
        return False
    if not task_exists(profile_id):
        return True
    rc, _, err = _run_schtasks(
        ["/Delete", "/TN", _task_name(profile_id), "/F"]
    )
    if rc == 0:
        log.info("Task Scheduler: rimossa task per profilo id=%s", profile_id)
        return True
    log.warning(
        "Task Scheduler: rimozione fallita id=%s: %s", profile_id, err.strip()
    )
    return False


def ensure_folder() -> None:
    """No-op: schtasks crea automaticamente la cartella «\\Scrinium\\»
    al primo /Create con quel path."""
    return


# ---------------------------------------------------------------------------
# Sync di alto livello
# ---------------------------------------------------------------------------

def current_executable_command() -> tuple[str, str]:
    """Restituisce (exe_path, arg_prefix) per lanciare Scrinium con un
    flag aggiuntivo. ``arg_prefix`` è la stringa di argomenti che precede
    eventuali nuovi argomenti (es. ``-m scrinium`` in dev, vuoto se exe).
    """
    exe = Path(sys.executable).resolve()
    if exe.name.lower() == "scrinium.exe":
        return str(exe), ""
    # In sviluppo: python.exe + -m scrinium
    return str(exe), "-m scrinium "


def sync_profiles(profiles, get_cron) -> tuple[int, int, list[str]]:
    """Sincronizza le task Windows con la lista profili.

    Per ogni profilo con cron valido: registra/aggiorna la task.
    Per ogni profilo senza cron o non più presente: elimina la task.

    ``get_cron(profile)`` deve restituire la stringa cron del profilo
    (passato come callable per non assumere il tipo concreto).

    Restituisce (registrate, rimosse, errori).
    """
    if not is_supported():
        return 0, 0, ["non-Windows"]

    exe, arg_prefix = current_executable_command()
    desired_ids = set()
    registered = 0
    errors: list[str] = []

    for p in profiles:
        cron = (get_cron(p) or "").strip()
        if not cron:
            continue
        desired_ids.add(p.id)
        ok, msg = register_task(
            profile_name=p.name,
            profile_id=p.id,
            cron=cron,
            exe_path=exe,
            arguments=f"{arg_prefix}--run-profile {p.id}",
        )
        if ok:
            registered += 1
        else:
            errors.append(f"{p.name}: {msg}")

    # Rimuovi task orfane
    removed = 0
    for tid in list_managed_task_ids():
        if tid not in desired_ids:
            if unregister_task(tid):
                removed += 1

    log.info(
        "Task Scheduler sync: %d registrate, %d rimosse, %d errori",
        registered, removed, len(errors),
    )
    return registered, removed, errors


def remove_all_tasks() -> int:
    """Elimina tutte le task ``\\Scrinium\\*``. Utile se l'utente passa
    alla modalità in-app."""
    if not is_supported():
        return 0
    removed = 0
    for tid in list_managed_task_ids():
        if unregister_task(tid):
            removed += 1
    return removed
