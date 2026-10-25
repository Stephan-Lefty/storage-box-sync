"""Einstellungsfenster."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from .. import config as konfig_modul
from .. import lock, paths, rclone, schedule, state, sync
from ..config import STANDARD_AUSNAHMEN, Einstellungen, KonfigFehler
from .gemeinsam import Laeufer, lade_einstellungen, oeffne, symbol_fuer

KONFLIKT_REGELN = [
    ("newer", "Die neuere Fassung gewinnt (empfohlen)"),
    ("older", "Die ältere Fassung gewinnt"),
    ("larger", "Die größere Datei gewinnt"),
    ("smaller", "Die kleinere Datei gewinnt"),
    ("none", "Nichts entscheiden, beide Fassungen behalten"),
]

VERLIERER = [
    ("pathname", "Verlierer umbenennen, z. B. Brief.konflikt-pc.odt"),
    ("num", "Verlierer durchnummerieren, z. B. Brief.conflict1.odt"),
    ("delete", "Verlierer löschen (Vorsicht)"),
]


class Fenster(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.e = lade_einstellungen()
        self.laeufer: Laeufer | None = None
        self.passwort_geaendert = False

        self.setWindowTitle("Storage Box – Abgleich")
        self.resize(820, 680)

        aussen = QVBoxLayout(self)
        self.reiter = QTabWidget()
        aussen.addWidget(self.reiter, 1)

        self.reiter.addTab(self._reiter_verbindung(), "Verbindung")
        self.reiter.addTab(self._reiter_ordner(), "Ordner")
        self.reiter.addTab(self._reiter_schutz(), "Konflikte und Schutz")
        self.reiter.addTab(self._reiter_zeitplan(), "Zeitplan")
        self.reiter.addTab(self._reiter_ausnahmen(), "Ausnahmen")
        self.reiter.addTab(self._reiter_protokolle(), "Protokolle")

        # Statuszeile
        self.zustandsschild = QLabel()
        self.zustandsschild.setWordWrap(True)
        aussen.addWidget(self.zustandsschild)

        # Ausgabe der Läufe
        self.ausgabe = QPlainTextEdit()
        self.ausgabe.setReadOnly(True)
        self.ausgabe.setMaximumBlockCount(4000)
        schrift = QFont("monospace")
        schrift.setStyleHint(QFont.StyleHint.Monospace)
        self.ausgabe.setFont(schrift)
        aussen.addWidget(self.ausgabe, 1)

        # Knöpfe
        knopfreihe = QHBoxLayout()
        self.k_speichern = QPushButton("Speichern")
        self.k_speichern.clicked.connect(self.speichern)
        self.k_probe = QPushButton("Probelauf")
        self.k_probe.clicked.connect(lambda: self.starte(probelauf=True))
        self.k_grund = QPushButton("Grundlauf")
        self.k_grund.clicked.connect(self.grundlauf)
        self.k_jetzt = QPushButton("Jetzt abgleichen")
        self.k_jetzt.clicked.connect(lambda: self.starte())
        self.k_ordner = QPushButton("Ordner öffnen")
        self.k_ordner.clicked.connect(lambda: oeffne(self.e.lokal_pfad))
        k_zu = QPushButton("Schließen")
        k_zu.clicked.connect(self.close)

        for knopf in (self.k_speichern, self.k_probe, self.k_grund, self.k_jetzt, self.k_ordner):
            knopfreihe.addWidget(knopf)
        knopfreihe.addStretch(1)
        knopfreihe.addWidget(k_zu)
        aussen.addLayout(knopfreihe)

        self.in_felder_schreiben()
        self.zustand_zeigen()

        self.takt = QTimer(self)
        self.takt.timeout.connect(self.zustand_zeigen)
        self.takt.start(5000)

    # ------------------------------------------------------------------
    #  Reiter
    # ------------------------------------------------------------------

    def _reiter_verbindung(self) -> QWidget:
        seite = QWidget()
        form = QFormLayout(seite)

        self.f_host = QLineEdit()
        self.f_host.setPlaceholderText("uXXXXXX.your-storagebox.de")
        self.f_benutzer = QLineEdit()
        self.f_benutzer.setPlaceholderText("uXXXXXX oder uXXXXXX-subX")
        self.f_port = QComboBox()
        self.f_port.addItem("23 – schneller SSH-Dienst", 23)
        self.f_port.addItem("22 – immer verfügbar", 22)
        self.f_fern = QLineEdit()
        self.f_fern.setPlaceholderText("/  oder  /daten")
        self.f_passwort = QLineEdit()
        self.f_passwort.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_passwort.setPlaceholderText("unverändert lassen, wenn leer")
        self.f_passwort.textEdited.connect(lambda _: setattr(self, "passwort_geaendert", True))

        form.addRow("Server", self.f_host)
        form.addRow("Benutzer", self.f_benutzer)
        form.addRow("Port", self.f_port)
        form.addRow("Ordner auf der Box", self.f_fern)
        form.addRow("Passwort", self.f_passwort)

        k_pruefen = QPushButton("Verbindung prüfen")
        k_pruefen.clicked.connect(self.verbindung_pruefen)
        form.addRow("", k_pruefen)

        hinweis = QLabel(
            "Das Passwort wird in der rclone-Form verschleiert gespeichert – das ist "
            "keine Verschlüsselung. Wer die Datei lesen kann, kann es zurückrechnen. "
            "Unter Linux liegt sie mit Rechten 600 im eigenen Konto.\n\n"
            "Die Storage Box erlaubt zehn Verbindungen gleichzeitig, über alle "
            "Protokolle zusammen."
        )
        hinweis.setWordWrap(True)
        form.addRow(hinweis)
        return seite

    def _reiter_ordner(self) -> QWidget:
        seite = QWidget()
        form = QFormLayout(seite)

        reihe = QHBoxLayout()
        self.f_lokal = QLineEdit()
        k_waehlen = QPushButton("Auswählen …")
        k_waehlen.clicked.connect(self.ordner_waehlen)
        reihe.addWidget(self.f_lokal, 1)
        reihe.addWidget(k_waehlen)
        huelle = QWidget()
        huelle.setLayout(reihe)
        form.addRow("Örtlicher Ordner", huelle)

        self.f_rechnername = QLineEdit()
        form.addRow("Name dieses Rechners", self.f_rechnername)

        self.f_leere_ordner = QCheckBox("Leere Ordner mit übertragen")
        form.addRow("", self.f_leere_ordner)

        self.f_zugriffspruefung = QCheckBox(
            "Prüfdatei auf beiden Seiten verlangen (dringend empfohlen)"
        )
        form.addRow("", self.f_zugriffspruefung)

        self.f_pruefdatei = QLineEdit()
        form.addRow("Name der Prüfdatei", self.f_pruefdatei)

        hinweis = QLabel(
            "Die Prüfdatei ist die wichtigste Sicherung: fehlt sie auf einer Seite, "
            "bricht der Abgleich ab. Genau das verhindert, dass ein nicht "
            "eingehängtes Laufwerk als „alles gelöscht“ gedeutet wird und die Box "
            "leer räumt."
        )
        hinweis.setWordWrap(True)
        form.addRow(hinweis)

        k_vorbereiten = QPushButton("Ordner und Prüfdateien anlegen")
        k_vorbereiten.clicked.connect(self.vorbereiten)
        form.addRow("", k_vorbereiten)
        return seite

    def _reiter_schutz(self) -> QWidget:
        seite = QWidget()
        aussen = QVBoxLayout(seite)

        kasten = QGroupBox("Wenn eine Datei auf beiden Seiten geändert wurde")
        form = QFormLayout(kasten)
        self.f_konflikt = QComboBox()
        for wert, text in KONFLIKT_REGELN:
            self.f_konflikt.addItem(text, wert)
        self.f_verlierer = QComboBox()
        for wert, text in VERLIERER:
            self.f_verlierer.addItem(text, wert)
        form.addRow("Entscheidung", self.f_konflikt)
        form.addRow("Unterlegene Fassung", self.f_verlierer)
        aussen.addWidget(kasten)

        kasten2 = QGroupBox("Schutz vor Massenverlust")
        form2 = QFormLayout(kasten2)
        self.f_max_loeschen = QSpinBox()
        self.f_max_loeschen.setRange(1, 100)
        self.f_max_loeschen.setSuffix(" %")
        form2.addRow("Abbruch, wenn mehr gelöscht würde als", self.f_max_loeschen)
        self.f_uebertragungen = QSpinBox()
        self.f_uebertragungen.setRange(1, 8)
        form2.addRow("Gleichzeitige Übertragungen", self.f_uebertragungen)
        aussen.addWidget(kasten2)

        kasten3 = QGroupBox("Mehrere Rechner")
        form3 = QFormLayout(kasten3)
        self.f_fernsperre = QCheckBox("Sperre auf der Box ablegen, solange abgeglichen wird")
        form3.addRow("", self.f_fernsperre)
        self.f_sperre_minuten = QSpinBox()
        self.f_sperre_minuten.setRange(5, 720)
        self.f_sperre_minuten.setSuffix(" Minuten")
        form3.addRow("Fremde Sperre gilt danach als verwaist", self.f_sperre_minuten)
        reihe = QHBoxLayout()
        k_sperren = QPushButton("Sperren ansehen")
        k_sperren.clicked.connect(self.sperren_zeigen)
        k_loesen = QPushButton("Eigene Sperre lösen")
        k_loesen.clicked.connect(self.sperre_loesen)
        reihe.addWidget(k_sperren)
        reihe.addWidget(k_loesen)
        reihe.addStretch(1)
        huelle = QWidget()
        huelle.setLayout(reihe)
        form3.addRow("", huelle)
        aussen.addWidget(kasten3)
        aussen.addStretch(1)
        return seite

    def _reiter_zeitplan(self) -> QWidget:
        seite = QWidget()
        form = QFormLayout(seite)
        self.f_beim_start = QCheckBox("Beim Start des Rechners (mit drei Minuten Vorlauf)")
        self.f_stuendlich = QCheckBox("Zusätzlich stündlich")
        form.addRow("", self.f_beim_start)
        form.addRow("", self.f_stuendlich)

        reihe = QHBoxLayout()
        k_ein = QPushButton("Zeitplan einrichten")
        k_ein.clicked.connect(self.zeitplan_ein)
        k_aus = QPushButton("Zeitplan entfernen")
        k_aus.clicked.connect(self.zeitplan_aus)
        reihe.addWidget(k_ein)
        reihe.addWidget(k_aus)
        reihe.addStretch(1)
        huelle = QWidget()
        huelle.setLayout(reihe)
        form.addRow("", huelle)

        self.zeitplan_text = QPlainTextEdit()
        self.zeitplan_text.setReadOnly(True)
        self.zeitplan_text.setMaximumHeight(160)
        form.addRow(self.zeitplan_text)
        return seite

    def _reiter_ausnahmen(self) -> QWidget:
        seite = QWidget()
        aussen = QVBoxLayout(seite)
        aussen.addWidget(QLabel(
            "Eine Regel je Zeile, in der Schreibweise von rclone: „- Muster“ "
            "schließt aus, „+ Muster“ nimmt ausdrücklich mit.\n"
            "Nach einer Änderung ist ein neuer Grundlauf nötig."
        ))
        self.f_ausnahmen = QPlainTextEdit()
        schrift = QFont("monospace")
        schrift.setStyleHint(QFont.StyleHint.Monospace)
        self.f_ausnahmen.setFont(schrift)
        aussen.addWidget(self.f_ausnahmen, 1)
        k_zurueck = QPushButton("Auf die Vorgaben zurücksetzen")
        k_zurueck.clicked.connect(
            lambda: self.f_ausnahmen.setPlainText("\n".join(STANDARD_AUSNAHMEN))
        )
        aussen.addWidget(k_zurueck)
        return seite

    def _reiter_protokolle(self) -> QWidget:
        seite = QWidget()
        aussen = QHBoxLayout(seite)
        self.protokoll_liste = QListWidget()
        self.protokoll_liste.setMaximumWidth(260)
        self.protokoll_liste.currentTextChanged.connect(self.protokoll_zeigen)
        aussen.addWidget(self.protokoll_liste)
        self.protokoll_text = QPlainTextEdit()
        self.protokoll_text.setReadOnly(True)
        schrift = QFont("monospace")
        schrift.setStyleHint(QFont.StyleHint.Monospace)
        self.protokoll_text.setFont(schrift)
        aussen.addWidget(self.protokoll_text, 1)
        self.protokolle_laden()
        return seite

    # ------------------------------------------------------------------
    #  Felder und Einstellungen
    # ------------------------------------------------------------------

    def in_felder_schreiben(self) -> None:
        e = self.e
        self.f_host.setText(e.host)
        self.f_benutzer.setText(e.benutzer)
        self.f_port.setCurrentIndex(0 if e.port == 23 else 1)
        self.f_fern.setText(e.fern)
        self.f_passwort.clear()
        self.passwort_geaendert = False

        self.f_lokal.setText(e.lokal)
        self.f_rechnername.setText(e.rechnername)
        self.f_leere_ordner.setChecked(e.leere_ordner)
        self.f_zugriffspruefung.setChecked(e.zugriffspruefung)
        self.f_pruefdatei.setText(e.pruefdatei)

        self.f_konflikt.setCurrentIndex(
            max(0, [w for w, _ in KONFLIKT_REGELN].index(e.konflikt_regel))
            if e.konflikt_regel in [w for w, _ in KONFLIKT_REGELN] else 0
        )
        self.f_verlierer.setCurrentIndex(
            [w for w, _ in VERLIERER].index(e.konflikt_verlierer)
            if e.konflikt_verlierer in [w for w, _ in VERLIERER] else 0
        )
        self.f_max_loeschen.setValue(e.max_loeschen)
        self.f_uebertragungen.setValue(e.uebertragungen)
        self.f_fernsperre.setChecked(e.fernsperre)
        self.f_sperre_minuten.setValue(e.sperre_minuten)

        self.f_beim_start.setChecked(e.zeitplan_beim_start)
        self.f_stuendlich.setChecked(e.zeitplan_stuendlich)
        self.f_ausnahmen.setPlainText("\n".join(e.ausnahmen))

    def aus_feldern_lesen(self) -> Einstellungen:
        e = self.e
        e.host = self.f_host.text().strip()
        e.benutzer = self.f_benutzer.text().strip()
        e.port = int(self.f_port.currentData())
        e.fern = self.f_fern.text().strip() or "/"
        e.lokal = self.f_lokal.text().strip()
        e.rechnername = self.f_rechnername.text().strip() or e.rechnername
        e.leere_ordner = self.f_leere_ordner.isChecked()
        e.zugriffspruefung = self.f_zugriffspruefung.isChecked()
        e.pruefdatei = self.f_pruefdatei.text().strip() or "RCLONE_TEST"
        e.konflikt_regel = self.f_konflikt.currentData()
        e.konflikt_verlierer = self.f_verlierer.currentData()
        e.max_loeschen = self.f_max_loeschen.value()
        e.uebertragungen = self.f_uebertragungen.value()
        e.fernsperre = self.f_fernsperre.isChecked()
        e.sperre_minuten = self.f_sperre_minuten.value()
        e.zeitplan_beim_start = self.f_beim_start.isChecked()
        e.zeitplan_stuendlich = self.f_stuendlich.isChecked()
        e.ausnahmen = [z for z in self.f_ausnahmen.toPlainText().splitlines() if z.strip()]

        if self.passwort_geaendert and self.f_passwort.text():
            try:
                e.passwort = rclone.verschleiere(self.f_passwort.text())
            except (rclone.RcloneFehlt, RuntimeError) as fehler:
                self.melde("Das Passwort konnte nicht übernommen werden: " + str(fehler))
        return e

    def speichern(self) -> bool:
        e = self.aus_feldern_lesen()
        try:
            e.pruefe()
        except KonfigFehler as fehler:
            QMessageBox.warning(self, "Noch nicht vollständig", str(fehler))
            return False
        e.speichern()
        try:
            rclone.schreibe_rclone_konfig(e)
        except rclone.RcloneFehlt as fehler:
            self.melde(str(fehler))
        self.melde(f"Gespeichert: {paths.konfig_datei()}")
        self.f_passwort.clear()
        self.passwort_geaendert = False
        self.zustand_zeigen()
        return True

    # ------------------------------------------------------------------
    #  Handlungen
    # ------------------------------------------------------------------

    def melde(self, text: str) -> None:
        self.ausgabe.appendPlainText(text)

    def ordner_waehlen(self) -> None:
        gewaehlt = QFileDialog.getExistingDirectory(
            self, "Örtlichen Ordner wählen", self.f_lokal.text() or str(Path.home())
        )
        if gewaehlt:
            self.f_lokal.setText(gewaehlt)

    def verbindung_pruefen(self) -> None:
        e = self.aus_feldern_lesen()
        try:
            e.pruefe()
        except KonfigFehler as fehler:
            QMessageBox.warning(self, "Noch nicht vollständig", str(fehler))
            return
        try:
            rclone.schreibe_rclone_konfig(e)
            steht, auskunft = rclone.pruefe_verbindung(e)
        except rclone.RcloneFehlt as fehler:
            QMessageBox.critical(self, "rclone fehlt", str(fehler))
            return
        if steht:
            self.melde("Die Verbindung steht.")
            if auskunft:
                self.melde(auskunft)
        else:
            self.melde("Die Verbindung steht nicht:")
            self.melde(auskunft)

    def vorbereiten(self) -> None:
        if not self.speichern():
            return
        try:
            sync.vorbereiten(self.e, melde=self.melde)
            self.melde("Beide Seiten sind vorbereitet.")
        except (RuntimeError, rclone.RcloneFehlt) as fehler:
            self.melde(str(fehler))

    def grundlauf(self) -> None:
        antwort = QMessageBox.question(
            self,
            "Grundlauf",
            "Der Grundlauf vergleicht beide Seiten vollständig und bringt sie in "
            "Einklang. Bei Dateien, die es auf beiden Seiten gibt, gewinnt die "
            "neuere Fassung. Gelöscht wird dabei nichts.\n\nJetzt starten?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if antwort == QMessageBox.StandardButton.Yes:
            self.starte(grundlauf=True)

    def starte(self, grundlauf: bool = False, probelauf: bool = False) -> None:
        if self.laeufer and self.laeufer.isRunning():
            self.melde("Es läuft schon etwas.")
            return
        if not self.speichern():
            return
        if not grundlauf and sync.braucht_grundlauf(self.e):
            QMessageBox.information(
                self, "Grundlauf fehlt",
                "Vor dem ersten gewöhnlichen Abgleich muss einmal der Grundlauf "
                "laufen. Er bringt beide Seiten in Einklang.",
            )
            return

        self.ausgabe.clear()
        art = "Grundlauf" if grundlauf else ("Probelauf" if probelauf else "Abgleich")
        self.melde(f"{art} gestartet …\n")
        for knopf in (self.k_probe, self.k_grund, self.k_jetzt):
            knopf.setEnabled(False)

        self.laeufer = Laeufer(self.e, grundlauf=grundlauf, probelauf=probelauf)
        self.laeufer.zeile.connect(self.melde)
        self.laeufer.fertig.connect(self.lauf_fertig)
        self.laeufer.start()

    def lauf_fertig(self, rueckgabe: int, kurz: str, protokoll: str) -> None:
        self.melde("\n" + kurz)
        if protokoll:
            self.melde("Protokoll: " + protokoll)
        for knopf in (self.k_probe, self.k_grund, self.k_jetzt):
            knopf.setEnabled(True)
        self.e = lade_einstellungen()
        self.protokolle_laden()
        self.zustand_zeigen()

    def zeitplan_ein(self) -> None:
        if not self.speichern():
            return
        try:
            for zeile in schedule.einrichten(self.e):
                self.melde(zeile)
        except schedule.ZeitplanFehler as fehler:
            self.melde("Der Zeitplan ließ sich nicht einrichten: " + str(fehler))
        self.zeitplan_zeigen()

    def zeitplan_aus(self) -> None:
        for zeile in schedule.entfernen():
            self.melde(zeile)
        self.zeitplan_zeigen()

    def zeitplan_zeigen(self) -> None:
        aktiv, text = schedule.zustand()
        self.zeitplan_text.setPlainText(("aktiv\n\n" if aktiv else "") + text)

    def sperren_zeigen(self) -> None:
        try:
            sperren = lock.liste(self.aus_feldern_lesen())
        except rclone.RcloneFehlt as fehler:
            self.melde(str(fehler))
            return
        if not sperren:
            self.melde("Keine Sperre auf der Box.")
            return
        for s in sperren:
            self.melde(f"{s['name']}  seit {int(s['alter_minuten'])} Minuten")

    def sperre_loesen(self) -> None:
        try:
            anzahl = lock.alle_eigenen_loesen(self.aus_feldern_lesen())
        except rclone.RcloneFehlt as fehler:
            self.melde(str(fehler))
            return
        self.melde(f"{anzahl} eigene Sperre(n) entfernt.")

    def protokolle_laden(self) -> None:
        self.protokoll_liste.clear()
        for datei in state.protokolle(40):
            self.protokoll_liste.addItem(datei.name)

    def protokoll_zeigen(self, name: str) -> None:
        if not name:
            return
        datei = paths.protokoll_ordner() / name
        try:
            self.protokoll_text.setPlainText(datei.read_text(encoding="utf-8", errors="replace"))
        except OSError as fehler:
            self.protokoll_text.setPlainText(str(fehler))

    def zustand_zeigen(self) -> None:
        z = state.ermittle()
        self.setWindowIcon(symbol_fuer(z.stufe))
        self.zustandsschild.setText(f"<b>{z.kurz}</b><br>" + "<br>".join(z.lang))
        if self.reiter.currentIndex() == 3:
            self.zeitplan_zeigen()


def starte() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    fenster = Fenster()
    fenster.show()
    if hasattr(app, "exec"):
        return app.exec()        # type: ignore[union-attr]
    return 0
