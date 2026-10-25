"""Der Zweiweg-Abgleich selbst."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import config as konfig_modul
from . import lock, paths, rclone, state
from .config import Einstellungen

Melder = Callable[[str], None]


@dataclass
class Ergebnis:
    rueckgabe: int = 0
    art: str = "abgleich"
    protokoll: Path | None = None
    dauer: float = 0.0
    uebersprungen: bool = False
    meldung: str = ""
    letzte_zeilen: list[str] = field(default_factory=list)

    @property
    def gelungen(self) -> bool:
        return self.rueckgabe == 0 and not self.uebersprungen


def _suffixe(e: Einstellungen) -> str:
    eigen = re.sub(r"[^A-Za-z0-9._-]", "-", e.rechnername)[:24] or "hier"
    return f"konflikt-{eigen},konflikt-box"


def baue_befehl(e: Einstellungen, grundlauf: bool, probelauf: bool) -> list[str]:
    """Die rclone-Befehlszeile zusammensetzen - getrennt, damit prüfbar."""
    befehl = [
        "bisync",
        str(e.lokal_pfad),
        e.fernziel,
        "--workdir", str(paths.arbeits_ordner()),
        "--filters-file", str(paths.filter_datei()),
        "--max-delete", str(e.max_loeschen),
        "--transfers", str(e.uebertragungen),
        "--checkers", str(e.uebertragungen),
        "--sftp-concurrency", "2",
        "--retries", "3",
        "--low-level-retries", "10",
        "--timeout", "5m",
        "--contimeout", "1m",
        "--max-lock", "15m",
        "--resilient",
        "--recover",
        "--log-level", "INFO",
        "--stats", "20s",
        "--stats-one-line",
    ]

    if e.leere_ordner:
        befehl.append("--create-empty-src-dirs")

    if e.zugriffspruefung:
        befehl += ["--check-access", "--check-filename", e.pruefdatei]

    if e.konflikt_regel != "none":
        befehl += [
            "--conflict-resolve", e.konflikt_regel,
            "--conflict-loser", e.konflikt_verlierer,
            "--conflict-suffix", _suffixe(e),
        ]

    if grundlauf:
        if rclone.kann_resync_modus():
            befehl += ["--resync", "--resync-mode", "newer"]
        else:
            befehl.append("--resync")

    if probelauf:
        befehl.append("--dry-run")

    return befehl


def vorbereiten(e: Einstellungen, melde: Melder | None = None) -> None:
    """Ordner und Prüfdateien auf beiden Seiten anlegen."""
    def sag(text: str) -> None:
        if melde:
            melde(text)

    rclone.schreibe_rclone_konfig(e)
    konfig_modul.schreibe_ausnahmen(e)
    paths.lege_ordner_an()

    ordner = e.lokal_pfad
    ordner.mkdir(parents=True, exist_ok=True)

    sag(f"Ferner Ordner anlegen, falls nötig: {e.fernziel}")
    ergebnis = rclone.lauf("mkdir", e.fernziel, zeitgrenze=60)
    if ergebnis.returncode != 0:
        raise RuntimeError(
            "Der Ordner auf der Storage Box konnte nicht angelegt werden:\n"
            + (ergebnis.stderr or "").strip()
        )

    if not e.zugriffspruefung:
        return

    oertlich = ordner / e.pruefdatei
    if not oertlich.exists():
        sag(f"Prüfdatei anlegen: {oertlich}")
        oertlich.write_text(
            "Diese Datei gehört zu storage-box-sync.\n"
            "Fehlt sie, bricht der Abgleich ab - das schützt davor, dass ein\n"
            "nicht eingehängtes Laufwerk die Gegenseite leer räumt.\n"
            "Bitte nicht löschen.\n",
            encoding="utf-8",
        )

    sag("Prüfdatei auf die Box übertragen")
    ergebnis = rclone.lauf("copy", str(oertlich), e.fernziel, zeitgrenze=120)
    if ergebnis.returncode != 0:
        raise RuntimeError(
            "Die Prüfdatei konnte nicht auf die Box übertragen werden:\n"
            + (ergebnis.stderr or "").strip()
        )


def _hindernis(e: Einstellungen) -> str | None:
    """Gründe, aus denen gar nicht erst gestartet werden darf."""
    ordner = e.lokal_pfad
    if not ordner.is_dir():
        return f"Der Ordner {ordner} ist nicht vorhanden. Ist das Laufwerk eingehängt?"
    if e.zugriffspruefung and not (ordner / e.pruefdatei).exists():
        return (
            f"Die Prüfdatei {e.pruefdatei} fehlt in {ordner}.\n"
            "Das Laufwerk ist vermutlich nicht eingehängt. Der Abgleich wird "
            "abgebrochen, damit auf der Box nichts gelöscht wird."
        )
    if not paths.filter_datei().exists():
        konfig_modul.schreibe_ausnahmen(e)
    if not paths.rclone_konfig_datei().exists():
        rclone.schreibe_rclone_konfig(e)
    return None


def abgleichen(
    e: Einstellungen | None = None,
    grundlauf: bool = False,
    probelauf: bool = False,
    melde: Melder | None = None,
) -> Ergebnis:
    def sag(text: str) -> None:
        if melde:
            melde(text)

    if e is None:
        e = konfig_modul.laden()
    e.pruefe()
    rclone.pruefe_version()

    art = "grundlauf" if grundlauf else ("probelauf" if probelauf else "abgleich")
    beginn = time.time()

    if not state.sperre_setzen():
        sag("Auf diesem Rechner läuft bereits ein Abgleich.")
        return Ergebnis(0, art, uebersprungen=True,
                        meldung="Auf diesem Rechner läuft bereits ein Abgleich.")

    protokoll: Path | None = None
    sperre_geholt = False
    try:
        hindernis = _hindernis(e)
        if hindernis:
            sag(hindernis)
            state.schreibe_lauf(art, 10, beginn, None, hindernis)
            return Ergebnis(10, art, meldung=hindernis)

        lage = lock.nehmen(e)
        if not lage.erhalten:
            sag(lage.hinweis)
            return Ergebnis(0, art, uebersprungen=True, meldung=lage.hinweis)
        sperre_geholt = e.fernsperre

        befehl = baue_befehl(e, grundlauf=grundlauf, probelauf=probelauf)

        fehlende = rclone.unbekannte_schalter(befehl)
        if fehlende:
            text = (
                "Diese rclone-Fassung kennt folgende Schalter nicht: "
                + ", ".join(fehlende)
                + "\nBitte rclone auf eine neuere Fassung bringen."
            )
            sag(text)
            state.schreibe_lauf(art, 11, beginn, None, text)
            return Ergebnis(11, art, meldung=text)

        protokoll = state.neues_protokoll(art)
        zeilen: list[str] = []

        kopf = [
            f"storage-box-sync - {art}",
            f"Rechner:  {e.rechnername}",
            f"Örtlich:  {e.lokal_pfad}",
            f"Fern:     {e.fernziel}",
            f"Beginn:   {time.strftime('%d.%m.%Y %H:%M:%S')}",
            "Befehl:   rclone " + " ".join(befehl),
            "-" * 70,
        ]
        with protokoll.open("w", encoding="utf-8") as schreiber:
            schreiber.write("\n".join(kopf) + "\n")
            schreiber.flush()

            vollbefehl = [str(rclone.finde_rclone()), "--config",
                          str(paths.rclone_konfig_datei()), *befehl]
            prozess = subprocess.Popen(
                vollbefehl,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                **rclone.startoptionen(),
            )
            assert prozess.stdout is not None
            for zeile in prozess.stdout:
                zeile = zeile.rstrip("\n")
                schreiber.write(zeile + "\n")
                schreiber.flush()
                zeilen.append(zeile)
                sag(zeile)
            rueckgabe = prozess.wait()

            schluss = (
                f"{'-' * 70}\nEnde: {time.strftime('%d.%m.%Y %H:%M:%S')} - "
                f"Rückgabewert {rueckgabe}\n"
            )
            schreiber.write(schluss)

        if rueckgabe == 0 and grundlauf and not probelauf:
            e.grundlauf_erledigt = True
            e.speichern()
            sag("Grundlauf erledigt - künftige Läufe gleichen nur noch Änderungen ab.")

        meldung = "\n".join(zeilen[-25:])
        if not probelauf:
            state.schreibe_lauf(art, rueckgabe, beginn, protokoll, meldung)
            state.raeume_protokolle_auf()

        return Ergebnis(
            rueckgabe=rueckgabe,
            art=art,
            protokoll=protokoll,
            dauer=time.time() - beginn,
            meldung=meldung,
            letzte_zeilen=zeilen[-40:],
        )

    finally:
        if sperre_geholt:
            try:
                lock.freigeben(e)
            except Exception:
                pass
        state.sperre_loesen()


def braucht_grundlauf(e: Einstellungen) -> bool:
    """Liegen überhaupt Dateilisten eines früheren Laufs vor?"""
    if not e.grundlauf_erledigt:
        return True
    try:
        return not any(paths.arbeits_ordner().iterdir())
    except OSError:
        return True
