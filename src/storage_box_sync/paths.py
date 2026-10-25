"""Ablageorte für Konfiguration, Zustand und Protokolle - je Betriebssystem.

Linux    ~/.config/storage-box-sync          ~/.local/state/storage-box-sync
Windows  %APPDATA%\\storage-box-sync          %LOCALAPPDATA%\\storage-box-sync
macOS    ~/Library/Application Support/...   ~/Library/Logs/storage-box-sync
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ANWENDUNG = "storage-box-sync"


def _umgebung(name: str) -> Path | None:
    wert = os.environ.get(name)
    return Path(wert) if wert else None


def konfig_ordner() -> Path:
    if sys.platform == "win32":
        basis = _umgebung("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        basis = Path.home() / "Library" / "Application Support"
    else:
        basis = _umgebung("XDG_CONFIG_HOME") or Path.home() / ".config"
    return basis / ANWENDUNG


def zustand_ordner() -> Path:
    if sys.platform == "win32":
        basis = _umgebung("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        basis = Path.home() / "Library" / "Logs"
        return basis / ANWENDUNG
    else:
        basis = _umgebung("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return basis / ANWENDUNG


def arbeits_ordner() -> Path:
    """Arbeitsverzeichnis von rclone bisync (Dateilisten des letzten Laufs)."""
    return zustand_ordner() / "bisync"


def protokoll_ordner() -> Path:
    return zustand_ordner() / "protokolle"


def konfig_datei() -> Path:
    return konfig_ordner() / "einstellungen.json"


def rclone_konfig_datei() -> Path:
    """Eigene rclone-Konfiguration, damit die des Benutzers unberührt bleibt."""
    return konfig_ordner() / "rclone.conf"


def filter_datei() -> Path:
    return konfig_ordner() / "ausnahmen.txt"


def zustand_datei() -> Path:
    return zustand_ordner() / "zustand.json"


def sperr_datei() -> Path:
    """Örtliche Sperre: verhindert zwei Läufe auf demselben Rechner."""
    return zustand_ordner() / "lauf.lock"


def lege_ordner_an() -> None:
    for ordner in (konfig_ordner(), zustand_ordner(), arbeits_ordner(), protokoll_ordner()):
        ordner.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        try:
            konfig_ordner().chmod(0o700)
        except OSError:
            pass
