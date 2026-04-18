"""Installer / uninstaller autocontenuto per Scrinium.

Compilato con PyInstaller in un unico exe che include Scrinium.exe come
risorsa. All'esecuzione mostra un wizard Tkinter (installa) oppure, se
lanciato con `--uninstall`, avvia la procedura di rimozione.

Funzionalità:
- installazione in %LOCALAPPDATA%\\Programs\\Scrinium (nessun diritto admin)
  oppure in percorso scelto dall'utente
- scorciatoie su Desktop e nel menu Start (tramite VBScript, nessuna
  dipendenza esterna)
- registrazione in "App installate" di Windows (registry HKCU Uninstall)
- disinstallazione pulita con self-delete via batch differito
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Scrinium"
APP_VERSION = "1.0.1"
APP_PUBLISHER = (
    "Avv. Roberto Arcella e Commissione Informatica del "
    "Consiglio dell'Ordine degli Avvocati di Napoli"
)
APP_EXE = "Scrinium.exe"
UNINSTALL_KEY_NAME = "Scrinium"  # chiave in HKCU\...\Uninstall
UNINSTALL_REG_PATH = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\\" + UNINSTALL_KEY_NAME
)


def _resource_path(rel: str) -> Path:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return Path(base) / rel


def _default_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / APP_NAME


def _start_menu_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME


def _desktop_dir() -> Path:
    # Desktop utente
    return Path(os.path.join(os.environ.get("USERPROFILE", str(Path.home())), "Desktop"))


def _create_shortcut(lnk_path: Path, target: Path, working_dir: Path, description: str) -> None:
    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    vbs = f"""
Set WshShell = CreateObject("WScript.Shell")
Set shortcut = WshShell.CreateShortcut("{lnk_path}")
shortcut.TargetPath = "{target}"
shortcut.WorkingDirectory = "{working_dir}"
shortcut.Description = "{description}"
shortcut.Save
"""
    tmp = Path(tempfile.gettempdir()) / f"scrinium_mklnk_{os.getpid()}.vbs"
    tmp.write_text(vbs, encoding="utf-8")
    try:
        subprocess.run(
            ["cscript", "//nologo", str(tmp)],
            check=False,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    finally:
        tmp.unlink(missing_ok=True)


def _register_uninstaller(install_dir: Path, size_kb: int) -> None:
    uninst_exe = install_dir / "Scrinium-uninstaller.exe"
    # Scriviamo il setup.exe stesso (questo file) come uninstaller:
    # a install-time copiamo noi stessi lì.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, f"{APP_NAME}")
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
        winreg.SetValueEx(
            k, "InstallLocation", 0, winreg.REG_SZ, str(install_dir)
        )
        winreg.SetValueEx(
            k,
            "DisplayIcon",
            0,
            winreg.REG_SZ,
            str(install_dir / APP_EXE),
        )
        winreg.SetValueEx(
            k,
            "UninstallString",
            0,
            winreg.REG_SZ,
            f'"{uninst_exe}" --uninstall',
        )
        winreg.SetValueEx(
            k, "QuietUninstallString", 0, winreg.REG_SZ,
            f'"{uninst_exe}" --uninstall --silent',
        )
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)


def _unregister_uninstaller() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Uninstall: lancia batch differito che elimina installdir dopo la chiusura
# ---------------------------------------------------------------------------


def _self_delete(install_dir: Path) -> None:
    """Lancia un batch in background che attende la chiusura di questo
    processo ed elimina la cartella di installazione."""
    bat = Path(tempfile.gettempdir()) / "scrinium_uninstall.bat"
    lines = [
        "@echo off",
        "ping 127.0.0.1 -n 2 >nul",  # attesa ~1s
        f'rmdir /s /q "{install_dir}"',
        f'del /q "{bat}"',
    ]
    bat.write_text("\r\n".join(lines), encoding="mbcs")
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        creationflags=0x08000008,  # DETACHED_PROCESS | CREATE_NO_WINDOW
        close_fds=True,
    )


def _remove_shortcuts() -> None:
    for lnk in (
        _desktop_dir() / f"{APP_NAME}.lnk",
        _start_menu_dir() / f"{APP_NAME}.lnk",
    ):
        try:
            lnk.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        _start_menu_dir().rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# GUI installer
# ---------------------------------------------------------------------------


class InstallerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Installazione {APP_NAME} {APP_VERSION}")
        self.geometry("560x400")
        self.resizable(False, False)
        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self.install_dir = tk.StringVar(value=str(_default_install_dir()))
        self.make_desktop = tk.BooleanVar(value=True)
        self.make_start_menu = tk.BooleanVar(value=True)
        self.launch_after = tk.BooleanVar(value=True)

        self.container = ttk.Frame(self, padding=20)
        self.container.pack(fill="both", expand=True)

        self.footer = ttk.Frame(self, padding=(20, 10))
        self.footer.pack(fill="x")
        self.btn_back = ttk.Button(self.footer, text="Indietro", command=self._back, state="disabled")
        self.btn_next = ttk.Button(self.footer, text="Avanti", command=self._next)
        self.btn_cancel = ttk.Button(self.footer, text="Annulla", command=self.destroy)
        self.btn_back.pack(side="left")
        self.btn_cancel.pack(side="right")
        self.btn_next.pack(side="right", padx=6)

        self.step = 0
        self._render_step()

    # --- step rendering ---
    def _clear(self) -> None:
        for w in self.container.winfo_children():
            w.destroy()

    def _render_step(self) -> None:
        self._clear()
        {0: self._step_welcome, 1: self._step_options, 2: self._step_install, 3: self._step_done}[self.step]()

    def _step_welcome(self) -> None:
        ttk.Label(
            self.container,
            text=f"Installazione di {APP_NAME}",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        ttk.Label(
            self.container,
            text=(
                "Scrinium è un software libero e open source di backup "
                "incrementale, con verifica d'integrità SHA-256 e scheduler "
                "integrato.\n\n"
                "Pensato per avvocati, giuristi e studi professionali, e per "
                "chiunque abbia necessità di custodire con cura i propri "
                "dati e documenti.\n\n"
                f"Versione: {APP_VERSION}\n\n"
                "Cliccare su Avanti per continuare."
            ),
            wraplength=500,
            justify="left",
        ).pack(anchor="w")
        self.btn_back.config(state="disabled")
        self.btn_next.config(text="Avanti")

    def _step_options(self) -> None:
        ttk.Label(
            self.container, text="Opzioni di installazione",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(self.container, text="Cartella di installazione:").pack(anchor="w")
        row = ttk.Frame(self.container)
        row.pack(fill="x", pady=4)
        ttk.Entry(row, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Sfoglia...", command=self._pick_dir).pack(side="left", padx=6)
        ttk.Label(
            self.container,
            text="Default: %LOCALAPPDATA%\\Programs\\Scrinium (nessun diritto amministratore richiesto).",
            foreground="#666",
        ).pack(anchor="w", pady=(0, 14))

        ttk.Checkbutton(
            self.container, text="Crea scorciatoia sul Desktop",
            variable=self.make_desktop,
        ).pack(anchor="w")
        ttk.Checkbutton(
            self.container, text="Crea voce nel menu Start",
            variable=self.make_start_menu,
        ).pack(anchor="w")
        ttk.Checkbutton(
            self.container, text=f"Avvia {APP_NAME} al termine dell'installazione",
            variable=self.launch_after,
        ).pack(anchor="w")

        self.btn_back.config(state="normal")
        self.btn_next.config(text="Installa")

    def _step_install(self) -> None:
        ttk.Label(
            self.container, text="Installazione in corso...",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        self.lbl_status = ttk.Label(self.container, text="Preparazione...")
        self.lbl_status.pack(anchor="w", pady=(0, 8))
        self.bar = ttk.Progressbar(self.container, mode="indeterminate")
        self.bar.pack(fill="x")
        self.bar.start(10)

        self.btn_back.config(state="disabled")
        self.btn_next.config(state="disabled")
        self.btn_cancel.config(state="disabled")

        threading.Thread(target=self._do_install, daemon=True).start()

    def _step_done(self) -> None:
        ttk.Label(
            self.container, text="Installazione completata",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        ttk.Label(
            self.container,
            text=(
                f"{APP_NAME} è stato installato in:\n{self.install_dir.get()}\n\n"
                "Per disinstallare, utilizzare 'App installate' di Windows "
                "oppure eseguire Scrinium-uninstaller.exe nella cartella di installazione."
            ),
            wraplength=500,
            justify="left",
        ).pack(anchor="w")
        self.btn_back.config(state="disabled")
        self.btn_next.config(text="Fine", state="normal", command=self._finish)
        self.btn_cancel.config(state="disabled")

    # --- actions ---
    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.install_dir.get())
        if d:
            self.install_dir.set(os.path.join(d, APP_NAME) if not d.endswith(APP_NAME) else d)

    def _next(self) -> None:
        if self.step < 3:
            self.step += 1
            self._render_step()

    def _back(self) -> None:
        if self.step > 0:
            self.step -= 1
            self._render_step()

    def _finish(self) -> None:
        if self.launch_after.get():
            try:
                subprocess.Popen(
                    [str(Path(self.install_dir.get()) / APP_EXE)],
                    creationflags=0x00000008,
                )
            except Exception:
                pass
        self.destroy()

    # --- install logic ---
    def _do_install(self) -> None:
        try:
            install_dir = Path(self.install_dir.get())
            install_dir.mkdir(parents=True, exist_ok=True)

            self._set_status("Copia di Scrinium.exe...")
            src_exe = _resource_path(APP_EXE)
            dst_exe = install_dir / APP_EXE
            shutil.copy2(src_exe, dst_exe)

            self._set_status("Copia dell'uninstaller...")
            # Copiamo questo stesso exe come uninstaller nella install dir
            uninst_dst = install_dir / "Scrinium-uninstaller.exe"
            shutil.copy2(sys.executable, uninst_dst)

            if self.make_desktop.get():
                self._set_status("Creazione scorciatoia Desktop...")
                _create_shortcut(
                    _desktop_dir() / f"{APP_NAME}.lnk",
                    dst_exe, install_dir, f"{APP_NAME} — Backup e custodia documenti",
                )
            if self.make_start_menu.get():
                self._set_status("Creazione voce menu Start...")
                _create_shortcut(
                    _start_menu_dir() / f"{APP_NAME}.lnk",
                    dst_exe, install_dir, f"{APP_NAME} — Backup e custodia documenti",
                )

            self._set_status("Registrazione in App installate...")
            size_kb = max(1, dst_exe.stat().st_size // 1024)
            _register_uninstaller(install_dir, size_kb)

            self.after(400, self._install_done)
        except Exception as e:
            self.after(0, lambda: self._install_failed(e))

    def _set_status(self, msg: str) -> None:
        self.after(0, lambda: self.lbl_status.config(text=msg))

    def _install_done(self) -> None:
        self.bar.stop()
        self.step = 3
        self._render_step()

    def _install_failed(self, err: Exception) -> None:
        self.bar.stop()
        messagebox.showerror("Installazione fallita", f"Si è verificato un errore:\n{err}")
        self.destroy()


# ---------------------------------------------------------------------------
# Uninstaller
# ---------------------------------------------------------------------------


def _read_install_dir_from_registry() -> Path | None:
    try:
        with winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH) as k:
            val, _ = winreg.QueryValueEx(k, "InstallLocation")
            return Path(val)
    except OSError:
        # Fallback: se noi stessi giriamo da dentro la cartella di installazione
        return Path(sys.executable).parent


def run_uninstall(silent: bool = False) -> int:
    install_dir = _read_install_dir_from_registry() or Path(sys.executable).parent

    if not silent:
        root = tk.Tk()
        root.withdraw()
        ans = messagebox.askyesno(
            f"Disinstallare {APP_NAME}?",
            f"Rimuovere {APP_NAME} dal computer?\n\n"
            f"Cartella: {install_dir}\n\n"
            "I profili di backup e i log in %APPDATA%\\Scrinium saranno "
            "conservati. I file già copiati nelle destinazioni dei backup "
            "NON saranno toccati.",
        )
        root.destroy()
        if not ans:
            return 1

    _remove_shortcuts()
    _unregister_uninstaller()
    _self_delete(install_dir)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    if "--uninstall" in sys.argv:
        return run_uninstall(silent="--silent" in sys.argv)
    # Admin non richiesto perché installiamo in %LOCALAPPDATA%.
    app = InstallerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
