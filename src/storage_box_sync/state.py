"""Zustand festhalten und auswerten - ohne systemd, damit es überall gleich ist."""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import paths
from .config import Einstellungen

# Nach so vielen Stunden ohne erfolgreichen Lauf gilt der Stand als veraltet
VERALTET_NACH_STUNDEN = 26

STUFEN_TEXT = {
    "uneingerichtet": "Noch nicht eingerichtet",
    "laeuft": "Abgleich läuft",
    "fehler": "Letzter Abgleich fehlgeschlagen",
    "veraltet": "Seit längerem kein Abgleich",
    "gut": "Abgeglichen",
    "unbekannt": "Noch kein Abgleich gelaufen",
}


@dataclass
class Zustand:
    stufe: str = "unbekannt"
    kurz: str = ""
    lang: list[str] = field(default_factory=list)
    ordner: str = ""
    protokoll: str | None = None

    def als_text(self) -> str:
        zeilen = [self.kurz] + self.lang
        return "\n".join(z for z in zeilen if z)


# ----------------------------------------------------------------------
#  Zustandsdatei
# ----------------------------------------------------------------------

def lies_lauf() -> dict:
    try:
        daten = json.loads(paths.zustand_datei().read_text(encoding="utf-8"))
        return daten if isinstance(daten, dict) else {}
    except (OSError, ValueError):
        return {}


def schreibe_lauf(
    art: str,
    rueckgabe: int,
    beginn: float,
    protokoll: Path | None,
    meldung: str = "",
) -> None:
    paths.lege_ordner_an()
    daten = {
        "art": art,
        "rueckgabe": rueckgabe,
        "beginn": beginn,
        "ende": time.time(),
        "rechner": socket.gethostname(),
        "protokoll": str(protokoll) if protokoll else None,
        "meldung": meldung[-2000:],
    }
    if rueckgabe == 0:
        daten["letzter_erfolg"] = daten["ende"]
    else:
        frueher = lies_lauf().get("letzter_erfolg")
        if frueher:
            daten["letzter_erfolg"] = frueher

    ziel = paths.zustand_datei()
    vorlaeufig = ziel.with_suffix(".json.neu")
    vorlaeufig.write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(vorlaeufig, ziel)


# ----------------------------------------------------------------------
#  Örtliche Sperre
# ----------------------------------------------------------------------

def prozess_laeuft(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        SYNCHRONIZE = 0x00100000
        kern = ctypes.windll.kernel32
        kennung = kern.OpenProcess(SYNCHRONIZE, False, pid)
        if kennung:
            kern.CloseHandle(kennung)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def laeuft_schon() -> bool:
    datei = paths.sperr_datei()
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    pid = int(daten.get("pid", 0))
    if prozess_laeuft(pid):
        return True
    # verwaiste Sperre
    datei.unlink(missing_ok=True)
    return False


def sperre_setzen() -> bool:
    if laeuft_schon():
        return False
    paths.lege_ordner_an()
    paths.sperr_datei().write_text(
        json.dumps({"pid": os.getpid(), "beginn": time.time()}),
        encoding="utf-8",
    )
    return True


def sperre_loesen() -> None:
    paths.sperr_datei().unlink(missing_ok=True)


# ----------------------------------------------------------------------
#  Protokolle
# ----------------------------------------------------------------------

def neues_protokoll(art: str) -> Path:
    paths.lege_ordner_an()
    stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    return paths.protokoll_ordner() / f"{stempel}_{art}.log"


def protokolle(anzahl: int = 20) -> list[Path]:
    try:
        dateien = sorted(
            paths.protokoll_ordner().glob("*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []
    return dateien[:anzahl]


def letztes_protokoll() -> Path | None:
    alle = protokolle(1)
    return alle[0] if alle else None


def raeume_protokolle_auf(behalten: int = 40) -> None:
    for alt in protokolle(500)[behalten:]:
        try:
            alt.unlink()
        except OSError:
            pass


# ----------------------------------------------------------------------
#  Auswertung
# ----------------------------------------------------------------------

def ordner_ist_da(e: Einstellungen) -> bool:
    """Liegt der örtliche Ordner wirklich vor - mit Prüfdatei als Beweis?"""
    ordner = e.lokal_pfad
    if not ordner.is_dir():
        return False
    if e.zugriffspruefung:
        return (ordner / e.pruefdatei).exists()
    return True


def ermittle(e: Einstellungen | None = None) -> Zustand:
    from . import config as konfig_modul

    if e is None:
        try:
            e = konfig_modul.laden()
        except konfig_modul.KonfigFehler as fehler:
            return Zustand("fehler", "Einstellungen unlesbar", [str(fehler)])

    z = Zustand(ordner=str(e.lokal_pfad) if e.lokal else "")

    try:
        e.pruefe()
    except konfig_modul.KonfigFehler as fehler:
        z.stufe = "uneingerichtet"
        z.kurz = STUFEN_TEXT["uneingerichtet"]
        z.lang = [str(fehler), "Einrichten mit: storage-box-sync einrichten"]
        return z

    if laeuft_schon():
        z.stufe = "laeuft"
        z.kurz = STUFEN_TEXT["laeuft"]
        z.lang = ["Der Abgleich läuft gerade."]
        return z

    if not e.lokal_pfad.is_dir():
        z.stufe = "fehler"
        z.kurz = "Örtlicher Ordner fehlt"
        z.lang = [f"Nicht vorhanden: {e.lokal_pfad}", "Ist das Laufwerk eingehängt?"]
        return z

    if e.zugriffspruefung and not (e.lokal_pfad / e.pruefdatei).exists():
        z.stufe = "fehler"
        z.kurz = "Laufwerk nicht eingehängt"
        z.lang = [
            f"Die Prüfdatei {e.pruefdatei} fehlt in {e.lokal_pfad}.",
            "Entweder ist das Laufwerk nicht eingehängt, oder die Einrichtung ist unvollständig.",
        ]
        return z

    if not e.grundlauf_erledigt:
        z.stufe = "unbekannt"
        z.kurz = "Grundlauf steht noch aus"
        z.lang = [
            "Der erste Abgleich bringt beide Seiten in Einklang.",
            "Starten mit: storage-box-sync grundlauf",
        ]
        return z

    lauf = lies_lauf()
    if not lauf:
        z.stufe = "unbekannt"
        z.kurz = STUFEN_TEXT["unbekannt"]
        z.lang = ["Es liegt noch kein Protokoll vor."]
        return z

    z.protokoll = lauf.get("protokoll")
    ende = lauf.get("ende")
    wann = datetime.fromtimestamp(ende).strftime("%d.%m.%Y %H:%M") if ende else "unbekannt"

    if lauf.get("rueckgabe", 1) != 0:
        z.stufe = "fehler"
        z.kurz = STUFEN_TEXT["fehler"]
        z.lang = [f"Versuch am {wann}, Rückgabewert {lauf.get('rueckgabe')}."]
        meldung = (lauf.get("meldung") or "").strip().splitlines()
        if meldung:
            z.lang.append(meldung[-1][:200])
        erfolg = lauf.get("letzter_erfolg")
        if erfolg:
            z.lang.append(
                "Letzter erfolgreicher Abgleich: "
                + datetime.fromtimestamp(erfolg).strftime("%d.%m.%Y %H:%M")
            )
        return z

    z.lang = [f"Letzter Abgleich: {wann}"]
    alter = datetime.now() - datetime.fromtimestamp(ende) if ende else timedelta(days=99)
    if alter > timedelta(hours=VERALTET_NACH_STUNDEN):
        z.stufe = "veraltet"
        z.kurz = f"Seit {int(alter.total_seconds() // 3600)} Stunden kein Abgleich"
    else:
        z.stufe = "gut"
        z.kurz = STUFEN_TEXT["gut"]
    return z
