"""Automatischer Lauf: systemd unter Linux, Aufgabenplanung unter Windows,
launchd unter macOS. Nach außen überall dieselben vier Befehle.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import paths
from .config import Einstellungen

DIENSTNAME = "storage-box-sync"
WIN_AUFGABE_START = "storage-box-sync (Anmeldung)"
WIN_AUFGABE_STUNDE = "storage-box-sync (stuendlich)"


class ZeitplanFehler(Exception):
    pass


# ----------------------------------------------------------------------
#  Welcher Befehl soll gestartet werden?
# ----------------------------------------------------------------------

def befehl_fuer_zeitplan(fenster: bool = False) -> list[str]:
    """Den Aufruf finden, der auch ohne geöffnete Sitzung funktioniert."""
    ordner = Path(sys.executable).parent
    name = "storage-box-sync.exe" if sys.platform == "win32" else "storage-box-sync"
    kandidaten = [ordner / name, ordner / "Scripts" / name]
    gefunden = shutil.which(name)
    if gefunden:
        kandidaten.insert(0, Path(gefunden))

    if sys.platform == "win32" and not fenster:
        # pythonw blitzt kein Konsolenfenster auf
        stiller = Path(sys.executable).with_name("pythonw.exe")
        if stiller.exists():
            return [str(stiller), "-m", "storage_box_sync", "abgleich", "--still"]

    for pfad in kandidaten:
        if pfad.exists():
            return [str(pfad), "abgleich", "--still"]

    return [sys.executable, "-m", "storage_box_sync", "abgleich", "--still"]


def _lauf(*args: str) -> subprocess.CompletedProcess:
    startopt = {}
    if sys.platform == "win32":
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startopt = {"startupinfo": info, "creationflags": subprocess.CREATE_NO_WINDOW}
    return subprocess.run(list(args), capture_output=True, text=True, timeout=60, **startopt)


# ----------------------------------------------------------------------
#  Linux: systemd im Benutzerkontext
# ----------------------------------------------------------------------

def _systemd_ordner() -> Path:
    basis = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(basis) / "systemd" / "user"


def _systemd_einrichten(e: Einstellungen) -> list[str]:
    ordner = _systemd_ordner()
    ordner.mkdir(parents=True, exist_ok=True)
    befehl = " ".join(f'"{t}"' if " " in t else t for t in befehl_fuer_zeitplan())

    dienst = f"""[Unit]
Description=Abgleich mit der Hetzner Storage Box
After=network-online.target
Wants=network-online.target
RequiresMountsFor={e.lokal_pfad}
ConditionPathIsDirectory={e.lokal_pfad}

[Service]
Type=oneshot
ExecStart={befehl}
Nice=10
IOSchedulingClass=idle
TimeoutStartSec=4h
"""
    (ordner / f"{DIENSTNAME}.service").write_text(dienst, encoding="utf-8")

    ausloeser = ["[Unit]", "Description=Zeitplan für den Abgleich mit der Storage Box", "", "[Timer]"]
    if e.zeitplan_beim_start:
        ausloeser.append("OnBootSec=3min")
        ausloeser.append("OnStartupSec=3min")
    if e.zeitplan_stuendlich:
        ausloeser.append("OnUnitActiveSec=1h")
        ausloeser.append("OnCalendar=hourly")
    ausloeser += [
        "Persistent=true",
        "RandomizedDelaySec=180",
        "AccuracySec=1min",
        f"Unit={DIENSTNAME}.service",
        "",
        "[Install]",
        "WantedBy=timers.target",
        "",
    ]
    (ordner / f"{DIENSTNAME}.timer").write_text("\n".join(ausloeser), encoding="utf-8")

    meldungen = [f"Einheiten geschrieben nach {ordner}"]
    _lauf("systemctl", "--user", "daemon-reload")
    ergebnis = _lauf("systemctl", "--user", "enable", "--now", f"{DIENSTNAME}.timer")
    if ergebnis.returncode != 0:
        raise ZeitplanFehler((ergebnis.stderr or ergebnis.stdout).strip())
    meldungen.append("Zeitplan ist aktiv.")

    linger = _lauf("loginctl", "show-user", os.environ.get("USER", ""), "-p", "Linger", "--value")
    if "no" in (linger.stdout or "").lower():
        meldungen.append(
            "Hinweis: Damit der Abgleich auch ohne angemeldete Sitzung läuft:\n"
            f"  sudo loginctl enable-linger {os.environ.get('USER', '')}"
        )
    return meldungen


def _systemd_entfernen() -> list[str]:
    _lauf("systemctl", "--user", "disable", "--now", f"{DIENSTNAME}.timer")
    ordner = _systemd_ordner()
    for name in (f"{DIENSTNAME}.timer", f"{DIENSTNAME}.service"):
        (ordner / name).unlink(missing_ok=True)
    _lauf("systemctl", "--user", "daemon-reload")
    return ["Zeitplan entfernt."]


def _systemd_zustand() -> tuple[bool, str]:
    ergebnis = _lauf("systemctl", "--user", "is-enabled", f"{DIENSTNAME}.timer")
    aktiv = (ergebnis.stdout or "").strip() == "enabled"
    if not aktiv:
        return False, "Kein Zeitplan eingerichtet."
    liste = _lauf("systemctl", "--user", "list-timers", f"{DIENSTNAME}.timer", "--no-pager")
    return True, (liste.stdout or "").strip()


# ----------------------------------------------------------------------
#  Windows: Aufgabenplanung
# ----------------------------------------------------------------------

def _win_befehlstext() -> str:
    teile = befehl_fuer_zeitplan()
    erster = f'"{teile[0]}"'
    rest = " ".join(teile[1:])
    return f"{erster} {rest}".strip()


def _win_einrichten(e: Einstellungen) -> list[str]:
    aufruf = _win_befehlstext()
    meldungen = []

    if e.zeitplan_beim_start:
        ergebnis = _lauf(
            "schtasks", "/Create", "/F", "/TN", WIN_AUFGABE_START,
            "/TR", aufruf, "/SC", "ONLOGON", "/DELAY", "0003:00", "/IT", "/RL", "LIMITED",
        )
        if ergebnis.returncode != 0:
            raise ZeitplanFehler((ergebnis.stderr or ergebnis.stdout).strip())
        meldungen.append(f"Aufgabe angelegt: {WIN_AUFGABE_START}")

    if e.zeitplan_stuendlich:
        ergebnis = _lauf(
            "schtasks", "/Create", "/F", "/TN", WIN_AUFGABE_STUNDE,
            "/TR", aufruf, "/SC", "HOURLY", "/MO", "1", "/IT", "/RL", "LIMITED",
        )
        if ergebnis.returncode != 0:
            raise ZeitplanFehler((ergebnis.stderr or ergebnis.stdout).strip())
        meldungen.append(f"Aufgabe angelegt: {WIN_AUFGABE_STUNDE}")

    return meldungen or ["Es war kein Auslöser gewählt - nichts angelegt."]


def _win_entfernen() -> list[str]:
    meldungen = []
    for name in (WIN_AUFGABE_START, WIN_AUFGABE_STUNDE):
        ergebnis = _lauf("schtasks", "/Delete", "/F", "/TN", name)
        if ergebnis.returncode == 0:
            meldungen.append(f"Aufgabe entfernt: {name}")
    return meldungen or ["Es war keine Aufgabe vorhanden."]


def _win_zustand() -> tuple[bool, str]:
    zeilen = []
    aktiv = False
    for name in (WIN_AUFGABE_START, WIN_AUFGABE_STUNDE):
        ergebnis = _lauf("schtasks", "/Query", "/TN", name, "/FO", "LIST")
        if ergebnis.returncode == 0:
            aktiv = True
            zeilen.append((ergebnis.stdout or "").strip())
    return aktiv, "\n".join(zeilen) if zeilen else "Kein Zeitplan eingerichtet."


# ----------------------------------------------------------------------
#  macOS: launchd
# ----------------------------------------------------------------------

def _mac_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "de.storage-box-sync.plist"


def _mac_einrichten(e: Einstellungen) -> list[str]:
    ziel = _mac_plist()
    ziel.parent.mkdir(parents=True, exist_ok=True)
    argumente = "".join(f"    <string>{t}</string>\n" for t in befehl_fuer_zeitplan())
    inhalt = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>de.storage-box-sync</string>
  <key>ProgramArguments</key>
  <array>
{argumente}  </array>
  <key>RunAtLoad</key><{'true' if e.zeitplan_beim_start else 'false'}/>
  <key>StartInterval</key><integer>{3600 if e.zeitplan_stuendlich else 0}</integer>
  <key>StandardErrorPath</key><string>{paths.protokoll_ordner() / 'launchd.log'}</string>
</dict>
</plist>
"""
    ziel.write_text(inhalt, encoding="utf-8")
    _lauf("launchctl", "unload", str(ziel))
    ergebnis = _lauf("launchctl", "load", str(ziel))
    if ergebnis.returncode != 0:
        raise ZeitplanFehler((ergebnis.stderr or ergebnis.stdout).strip())
    return [f"Zeitplan eingerichtet: {ziel}"]


def _mac_entfernen() -> list[str]:
    ziel = _mac_plist()
    _lauf("launchctl", "unload", str(ziel))
    ziel.unlink(missing_ok=True)
    return ["Zeitplan entfernt."]


def _mac_zustand() -> tuple[bool, str]:
    if not _mac_plist().exists():
        return False, "Kein Zeitplan eingerichtet."
    ergebnis = _lauf("launchctl", "list", "de.storage-box-sync")
    return True, (ergebnis.stdout or "Zeitplan ist eingerichtet.").strip()


# ----------------------------------------------------------------------
#  Gemeinsame Schnittstelle
# ----------------------------------------------------------------------

def einrichten(e: Einstellungen) -> list[str]:
    if sys.platform == "win32":
        return _win_einrichten(e)
    if sys.platform == "darwin":
        return _mac_einrichten(e)
    return _systemd_einrichten(e)


def entfernen() -> list[str]:
    if sys.platform == "win32":
        return _win_entfernen()
    if sys.platform == "darwin":
        return _mac_entfernen()
    return _systemd_entfernen()


def zustand() -> tuple[bool, str]:
    if sys.platform == "win32":
        return _win_zustand()
    if sys.platform == "darwin":
        return _mac_zustand()
    return _systemd_zustand()
