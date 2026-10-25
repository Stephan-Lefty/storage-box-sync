"""Gemeinsame Bausteine der Oberfläche."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

from .. import config as konfig_modul
from .. import sync
from ..config import Einstellungen

FARBEN = {
    "gut": "#2e7d32",
    "laeuft": "#1565c0",
    "veraltet": "#ef6c00",
    "fehler": "#c62828",
    "unbekannt": "#616161",
    "uneingerichtet": "#616161",
}

SYMBOLNAMEN = {
    "gut": ["vcs-normal", "emblem-success", "dialog-ok-apply"],
    "laeuft": ["vcs-update-required", "emblem-synchronizing", "view-refresh"],
    "veraltet": ["vcs-locally-modified", "emblem-important", "dialog-warning"],
    "fehler": ["vcs-conflicting", "emblem-error", "dialog-error"],
    "unbekannt": ["vcs-added", "dialog-question", "dialog-information"],
    "uneingerichtet": ["dialog-question", "dialog-information"],
}


def symbol_fuer(stufe: str) -> QIcon:
    """Symbol aus dem Thema, mit gemaltem Punkt als Rückfall (Windows)."""
    for name in SYMBOLNAMEN.get(stufe, SYMBOLNAMEN["unbekannt"]):
        gefunden = QIcon.fromTheme(name)
        if not gefunden.isNull():
            return gefunden
    return gemalter_punkt(FARBEN.get(stufe, "#616161"))


def gemalter_punkt(farbe: str, groesse: int = 64) -> QIcon:
    bild = QPixmap(groesse, groesse)
    bild.fill(QColor(0, 0, 0, 0))
    maler = QPainter(bild)
    maler.setRenderHint(QPainter.RenderHint.Antialiasing)
    maler.setBrush(QColor(farbe))
    maler.setPen(QColor(255, 255, 255, 210))
    rand = groesse // 10
    maler.drawEllipse(rand, rand, groesse - 2 * rand, groesse - 2 * rand)
    maler.end()
    return QIcon(bild)


def oeffne(ziel: str | Path) -> None:
    ziel = str(ziel)
    try:
        if sys.platform == "win32":
            os.startfile(ziel)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ziel])
        else:
            subprocess.Popen(["xdg-open", ziel],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


class Laeufer(QThread):
    """Lässt den Abgleich im Hintergrund laufen und meldet jede Zeile."""

    zeile = pyqtSignal(str)
    fertig = pyqtSignal(int, str, str)   # Rückgabewert, Kurztext, Protokollpfad

    def __init__(self, e: Einstellungen, grundlauf: bool = False, probelauf: bool = False):
        super().__init__()
        self.e = e
        self.grundlauf = grundlauf
        self.probelauf = probelauf

    def run(self) -> None:  # noqa: D102
        try:
            ergebnis = sync.abgleichen(
                self.e,
                grundlauf=self.grundlauf,
                probelauf=self.probelauf,
                melde=self.zeile.emit,
            )
        except Exception as fehler:            # bewusst weit gefasst
            self.fertig.emit(99, str(fehler), "")
            return

        if ergebnis.uebersprungen:
            kurz = "Übersprungen: " + ergebnis.meldung
        elif ergebnis.gelungen:
            kurz = f"Fertig in {int(ergebnis.dauer)} Sekunden."
            if self.probelauf:
                kurz += " Es war ein Probelauf, es wurde nichts verändert."
        else:
            kurz = f"Mit Fehler beendet (Rückgabewert {ergebnis.rueckgabe})."
        self.fertig.emit(ergebnis.rueckgabe, kurz, str(ergebnis.protokoll or ""))


def lade_einstellungen() -> Einstellungen:
    try:
        return konfig_modul.laden()
    except konfig_modul.KonfigFehler:
        return Einstellungen()
