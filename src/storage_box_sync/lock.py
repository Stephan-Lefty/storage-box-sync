"""Fernsperre auf der Storage Box.

Damit nie zwei Rechner gleichzeitig abgleichen, legt jeder Rechner vor dem
Lauf eine kleine Sperrdatei auf der Box ab und entfernt sie danach wieder.
Findet ein Rechner eine frische Sperre eines anderen, wartet er bis zum
nächsten Durchlauf.

Die Ablage liegt mit Absicht in einem eigenen Ordner, der vom Abgleich
ausgenommen ist:  /.storage-box-sync-sperren/
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
from dataclasses import dataclass

from . import rclone
from .config import Einstellungen

SPERRORDNER = "/.storage-box-sync-sperren"
NACHPRUEFUNG_SEKUNDEN = 3.0


@dataclass
class Sperrlage:
    erhalten: bool
    inhaber: str = ""
    alter_minuten: float = 0.0
    hinweis: str = ""


def _sauberer_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "unbekannt"


def _ziel(e: Einstellungen, dateiname: str = "") -> str:
    pfad = f"{e.remote_name}:{SPERRORDNER}"
    return f"{pfad}/{dateiname}" if dateiname else pfad


def eigener_name(e: Einstellungen) -> str:
    return _sauberer_name(e.rechnername or socket.gethostname()) + ".json"


def liste(e: Einstellungen) -> list[dict]:
    """Alle Sperren auf der Box, mit Alter in Minuten."""
    ergebnis = rclone.lauf("lsjson", _ziel(e), zeitgrenze=60)
    if ergebnis.returncode != 0:
        # Ordner gibt es noch nicht - das ist keine Störung
        return []
    try:
        eintraege = json.loads(ergebnis.stdout or "[]")
    except ValueError:
        return []

    jetzt = time.time()
    gefunden = []
    for eintrag in eintraege:
        if eintrag.get("IsDir"):
            continue
        stempel = eintrag.get("ModTime", "")
        alter = 0.0
        try:
            from datetime import datetime

            gesetzt = datetime.fromisoformat(stempel.replace("Z", "+00:00"))
            alter = max(0.0, (jetzt - gesetzt.timestamp()) / 60.0)
        except (ValueError, AttributeError):
            alter = 0.0
        gefunden.append({"name": eintrag.get("Name", ""), "alter_minuten": alter})
    return gefunden


def _schreibe_eigene(e: Einstellungen) -> bool:
    inhalt = json.dumps(
        {
            "rechner": e.rechnername,
            "pid": os.getpid(),
            "beginn": time.strftime("%Y-%m-%d %H:%M:%S"),
            "beginn_ts": time.time(),
        },
        ensure_ascii=False,
    )
    ergebnis = rclone.lauf("rcat", _ziel(e, eigener_name(e)), eingabe=inhalt, zeitgrenze=60)
    return ergebnis.returncode == 0


def _entferne(e: Einstellungen, dateiname: str) -> bool:
    ergebnis = rclone.lauf("deletefile", _ziel(e, dateiname), zeitgrenze=60)
    return ergebnis.returncode == 0


def nehmen(e: Einstellungen) -> Sperrlage:
    """Sperre holen. Scheitert freundlich, wenn ein anderer Rechner dran ist."""
    if not e.fernsperre:
        return Sperrlage(True, hinweis="Fernsperre ist abgeschaltet.")

    eigen = eigener_name(e)

    for sperre in liste(e):
        if sperre["name"] == eigen:
            continue
        if sperre["alter_minuten"] > e.sperre_minuten:
            # Verwaist - der andere Rechner ist offenbar abgestürzt
            _entferne(e, sperre["name"])
            continue
        return Sperrlage(
            False,
            inhaber=sperre["name"].removesuffix(".json"),
            alter_minuten=sperre["alter_minuten"],
            hinweis=(
                "Ein anderer Rechner gleicht gerade ab "
                f"({sperre['name'].removesuffix('.json')}, "
                f"seit {int(sperre['alter_minuten'])} Minuten). "
                "Dieser Lauf wird übersprungen."
            ),
        )

    if not _schreibe_eigene(e):
        return Sperrlage(False, hinweis="Die Sperre konnte nicht auf der Box abgelegt werden.")

    # Zweiter Blick: hat in derselben Sekunde ein anderer Rechner geschrieben?
    time.sleep(NACHPRUEFUNG_SEKUNDEN)
    fremde = [s for s in liste(e) if s["name"] != eigen and s["alter_minuten"] <= e.sperre_minuten]
    if fremde:
        # Der mit dem kleineren Namen gewinnt - willkürlich, aber auf allen
        # Rechnern gleich, also entscheidet es sich ohne weitere Absprache.
        gegner = sorted(s["name"] for s in fremde)[0]
        if gegner < eigen:
            _entferne(e, eigen)
            return Sperrlage(
                False,
                inhaber=gegner.removesuffix(".json"),
                hinweis=(
                    f"{gegner.removesuffix('.json')} war im selben Moment dran. "
                    "Dieser Lauf wird übersprungen."
                ),
            )

    return Sperrlage(True, hinweis="Sperre liegt auf der Box.")


def freigeben(e: Einstellungen) -> None:
    if not e.fernsperre:
        return
    _entferne(e, eigener_name(e))


def alle_eigenen_loesen(e: Einstellungen) -> int:
    """Notbremse: eigene Sperre entfernen, falls etwas hängen geblieben ist."""
    entfernt = 0
    for sperre in liste(e):
        if sperre["name"] == eigener_name(e) and _entferne(e, sperre["name"]):
            entfernt += 1
    return entfernt
