"""Einstellungen laden, prüfen und speichern."""

from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Any

from . import paths

STANDARD_AUSNAHMEN = [
    "- .zfs/**",
    "- .zfs",
    "- .Trash-*/**",
    "- .Trash/**",
    "- .TemporaryItems/**",
    "- lost+found/**",
    "- **/.directory",
    "- **/.DS_Store",
    "- **/._*",
    "- **/Thumbs.db",
    "- **/desktop.ini",
    "- **/~$*",
    "- **/*.tmp",
    "- **/.~lock.*#",
    "- **/.storage-box-sync-*",
    "- /.storage-box-sync-sperren/**",
]


class KonfigFehler(Exception):
    """Einstellungen fehlen oder sind unbrauchbar."""


@dataclass
class Einstellungen:
    # Was wird abgeglichen
    lokal: str = ""
    fern: str = "/"

    # Zugang zur Storage Box
    host: str = ""
    benutzer: str = ""
    port: int = 23
    passwort: str = ""          # mit "rclone obscure" verschleiert
    schluesseldatei: str = ""   # statt Passwort, wenn gesetzt

    # Verhalten
    rechnername: str = field(default_factory=socket.gethostname)
    konflikt_regel: str = "newer"       # newer | older | larger | smaller | none
    konflikt_verlierer: str = "pathname"  # pathname | num | delete
    max_loeschen: int = 50              # Abbruch, wenn mehr Prozent gelöscht würden
    uebertragungen: int = 4             # Storage Box erlaubt 10 Verbindungen gesamt
    zugriffspruefung: bool = True       # RCLONE_TEST auf beiden Seiten verlangen
    pruefdatei: str = "RCLONE_TEST"
    leere_ordner: bool = True

    # Mehrere Rechner
    fernsperre: bool = True
    sperre_minuten: int = 60            # fremde Sperre gilt danach als verwaist

    # Zeitplan
    zeitplan_beim_start: bool = True
    zeitplan_stuendlich: bool = True

    # Innerer Zustand
    grundlauf_erledigt: bool = False
    ausnahmen: list[str] = field(default_factory=lambda: list(STANDARD_AUSNAHMEN))

    # ------------------------------------------------------------------

    @property
    def remote_name(self) -> str:
        return "storagebox"

    @property
    def fernziel(self) -> str:
        pfad = self.fern.strip()
        if not pfad.startswith("/"):
            pfad = "/" + pfad
        return f"{self.remote_name}:{pfad}"

    @property
    def lokal_pfad(self) -> Path:
        return Path(os.path.expanduser(self.lokal))

    def pruefe(self) -> None:
        if not self.lokal:
            raise KonfigFehler("Es ist kein örtlicher Ordner eingetragen.")
        if not self.host:
            raise KonfigFehler("Es ist kein Server eingetragen (z. B. uXXXXX.your-storagebox.de).")
        if not self.benutzer:
            raise KonfigFehler("Es ist kein Benutzer eingetragen.")
        if not self.passwort and not self.schluesseldatei:
            raise KonfigFehler("Es ist weder ein Passwort noch eine Schlüsseldatei hinterlegt.")
        if self.konflikt_regel not in ("newer", "older", "larger", "smaller", "none"):
            raise KonfigFehler(f"Unbekannte Konfliktregel: {self.konflikt_regel}")
        if self.konflikt_verlierer not in ("pathname", "num", "delete"):
            raise KonfigFehler(f"Unbekannte Behandlung des Verlierers: {self.konflikt_verlierer}")
        if not 1 <= self.max_loeschen <= 100:
            raise KonfigFehler("Die Löschgrenze muss zwischen 1 und 100 Prozent liegen.")
        if not 1 <= self.uebertragungen <= 8:
            raise KonfigFehler(
                "Die Storage Box erlaubt zehn Verbindungen gleichzeitig. "
                "Mehr als acht Übertragungen sind nicht sinnvoll."
            )
        if self.sperre_minuten < 5:
            raise KonfigFehler("Die Sperre muss mindestens fünf Minuten gelten.")

    # ------------------------------------------------------------------

    def speichern(self) -> Path:
        paths.lege_ordner_an()
        ziel = paths.konfig_datei()
        vorlaeufig = ziel.with_suffix(".json.neu")
        vorlaeufig.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if sys.platform != "win32":
            try:
                vorlaeufig.chmod(0o600)
            except OSError:
                pass
        os.replace(vorlaeufig, ziel)
        schreibe_ausnahmen(self)
        return ziel


def laden() -> Einstellungen:
    datei = paths.konfig_datei()
    if not datei.exists():
        return Einstellungen()
    try:
        rohdaten: Any = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError) as fehler:
        raise KonfigFehler(f"Die Einstellungen sind unlesbar ({datei}): {fehler}") from fehler
    if not isinstance(rohdaten, dict):
        raise KonfigFehler(f"Die Einstellungen haben ein unerwartetes Format ({datei}).")

    erlaubt = {f.name for f in fields(Einstellungen)}
    bekannt = {k: v for k, v in rohdaten.items() if k in erlaubt}
    return Einstellungen(**bekannt)


def ist_eingerichtet() -> bool:
    try:
        laden().pruefe()
    except KonfigFehler:
        return False
    return True


def schreibe_ausnahmen(e: Einstellungen) -> Path:
    """Ausnahmen als rclone-Filterdatei ablegen."""
    paths.lege_ordner_an()
    datei = paths.filter_datei()
    zeilen = ["# von storage-box-sync erzeugt - Änderungen brauchen einen neuen Grundlauf"]
    zeilen += [z for z in e.ausnahmen if z.strip()]
    datei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return datei
