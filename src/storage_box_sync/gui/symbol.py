"""Symbol in der Kontrollleiste."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .. import config as konfig_modul
from .. import state, sync
from .gemeinsam import Laeufer, lade_einstellungen, oeffne, symbol_fuer

TAKT_MS = 20_000


class Anzeige:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.e = lade_einstellungen()
        self.laeufer: Laeufer | None = None
        self.letzte_stufe: str | None = None
        self.fenster = None

        self.symbol = QSystemTrayIcon()
        self.menue = QMenu()

        self.a_ordner = QAction("Ordner öffnen")
        self.a_ordner.triggered.connect(self.ordner_oeffnen)
        self.a_jetzt = QAction("Jetzt abgleichen")
        self.a_jetzt.triggered.connect(self.jetzt)
        self.a_einstellungen = QAction("Einstellungen …")
        self.a_einstellungen.triggered.connect(self.einstellungen)
        self.a_protokoll = QAction("Letztes Protokoll")
        self.a_protokoll.triggered.connect(self.protokoll)
        self.a_einzelheiten = QAction("Einzelheiten …")
        self.a_einzelheiten.triggered.connect(self.einzelheiten)
        self.a_ende = QAction("Beenden")
        self.a_ende.triggered.connect(self.app.quit)

        self.menue.addAction(self.a_ordner)
        self.menue.addAction(self.a_jetzt)
        self.menue.addSeparator()
        self.menue.addAction(self.a_einstellungen)
        self.menue.addAction(self.a_einzelheiten)
        self.menue.addAction(self.a_protokoll)
        self.menue.addSeparator()
        self.menue.addAction(self.a_ende)
        self.symbol.setContextMenu(self.menue)
        self.symbol.activated.connect(self.geklickt)

        self.aktualisiere()
        self.symbol.show()

        self.takt = QTimer()
        self.takt.timeout.connect(self.aktualisiere)
        self.takt.start(TAKT_MS)

    # ------------------------------------------------------------------

    def geklickt(self, grund) -> None:
        if grund == QSystemTrayIcon.ActivationReason.Trigger:
            self.ordner_oeffnen()

    def ordner_oeffnen(self) -> None:
        self.e = lade_einstellungen()
        if not self.e.lokal:
            self.einstellungen()
            return
        oeffne(self.e.lokal_pfad)

    def einstellungen(self) -> None:
        from .fenster import Fenster

        if self.fenster is None:
            self.fenster = Fenster()
        self.fenster.show()
        self.fenster.raise_()
        self.fenster.activateWindow()

    def protokoll(self) -> None:
        datei = state.letztes_protokoll()
        if datei:
            oeffne(datei)
        else:
            QMessageBox.information(None, "Storage Box", "Es liegt noch kein Protokoll vor.")

    def einzelheiten(self) -> None:
        z = state.ermittle()
        text = z.als_text()
        if z.ordner:
            text += f"\n\nOrdner: {z.ordner}"
        if z.protokoll:
            text += f"\nProtokoll: {z.protokoll}"
        QMessageBox.information(None, "Storage Box", text)

    def jetzt(self) -> None:
        if self.laeufer and self.laeufer.isRunning():
            return
        self.e = lade_einstellungen()
        try:
            self.e.pruefe()
        except konfig_modul.KonfigFehler:
            self.einstellungen()
            return
        grundlauf = sync.braucht_grundlauf(self.e)
        if grundlauf:
            self.einstellungen()
            QMessageBox.information(
                None, "Storage Box",
                "Vor dem ersten Abgleich muss einmal der Grundlauf laufen. "
                "Im Fenster findest du den Knopf dafür.",
            )
            return

        self.a_jetzt.setEnabled(False)
        self.laeufer = Laeufer(self.e)
        self.laeufer.fertig.connect(self.lauf_fertig)
        self.laeufer.start()
        self.aktualisiere()

    def lauf_fertig(self, rueckgabe: int, kurz: str, protokoll: str) -> None:
        self.a_jetzt.setEnabled(True)
        self.symbol.showMessage(
            "Storage Box", kurz,
            QSystemTrayIcon.MessageIcon.Information if rueckgabe == 0
            else QSystemTrayIcon.MessageIcon.Warning,
            6000,
        )
        self.aktualisiere()

    def aktualisiere(self) -> None:
        z = state.ermittle()
        self.symbol.setIcon(symbol_fuer(z.stufe))
        self.symbol.setToolTip("Storage Box — " + z.als_text())

        if z.stufe == "fehler" and self.letzte_stufe not in (None, "fehler"):
            self.symbol.showMessage(
                "Storage Box", z.kurz,
                QSystemTrayIcon.MessageIcon.Warning, 8000,
            )
        self.letzte_stufe = z.stufe


def starte() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Storage Box")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("In dieser Arbeitsumgebung gibt es keinen Platz für ein Symbol in der "
              "Kontrollleiste.", file=sys.stderr)
        return 1

    Anzeige(app)   # bleibt über die Ereignisschleife am Leben
    return app.exec()
