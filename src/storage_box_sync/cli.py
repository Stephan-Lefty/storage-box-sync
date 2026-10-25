"""Kommandozeile von storage-box-sync."""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from . import config as konfig_modul
from . import lock, paths, rclone, schedule, state, sync
from .config import Einstellungen, KonfigFehler

AUFRUF = "storage-box-sync"


def _schreib(text: str = "") -> None:
    print(text, flush=True)


def _frage(text: str, vorgabe: str = "") -> str:
    anzeige = f"{text} [{vorgabe}]: " if vorgabe else f"{text}: "
    try:
        eingabe = input(anzeige).strip()
    except EOFError:
        eingabe = ""
    return eingabe or vorgabe


def _ja_nein(text: str, vorgabe: bool = True) -> bool:
    hinweis = "J/n" if vorgabe else "j/N"
    antwort = _frage(f"{text} ({hinweis})").lower()
    if not antwort:
        return vorgabe
    return antwort.startswith(("j", "y"))


# ----------------------------------------------------------------------

def befehl_einrichten(args: argparse.Namespace) -> int:
    try:
        e = konfig_modul.laden()
    except KonfigFehler:
        e = Einstellungen()

    stapel = args.ohne_fragen

    if not stapel:
        _schreib("Einrichtung von storage-box-sync")
        _schreib("=" * 40)
        _schreib("Leere Eingabe übernimmt den Wert in Klammern.")
        _schreib()

    e.lokal = args.lokal or (e.lokal if stapel else _frage("Örtlicher Ordner", e.lokal))
    e.host = args.host or (e.host if stapel else _frage("Server der Storage Box", e.host))
    e.benutzer = args.benutzer or (e.benutzer if stapel else _frage("Benutzer", e.benutzer))
    port = args.port or (e.port if stapel else _frage("Port (23 schnell, 22 immer offen)", str(e.port)))
    try:
        e.port = int(port)
    except (TypeError, ValueError):
        _schreib("Der Port muss eine Zahl sein.")
        return 2
    e.fern = args.fern or (e.fern if stapel else _frage("Ordner auf der Box", e.fern))
    e.rechnername = args.rechnername or e.rechnername

    if args.passwort_von_stdin:
        klartext = sys.stdin.readline().rstrip("\n")
        e.passwort = rclone.verschleiere(klartext)
    elif not stapel:
        if e.passwort and not _ja_nein("Es ist ein Passwort hinterlegt. Neu eingeben?", False):
            pass
        else:
            klartext = getpass.getpass("Passwort der Storage Box (bleibt unsichtbar): ")
            if klartext:
                e.passwort = rclone.verschleiere(klartext)

    try:
        e.pruefe()
    except KonfigFehler as fehler:
        _schreib(f"\nDie Angaben sind noch nicht vollständig: {fehler}")
        return 2

    rclone.schreibe_rclone_konfig(e)
    _schreib("\nVerbindung prüfen …")
    steht, auskunft = rclone.pruefe_verbindung(e)
    if not steht:
        _schreib("Die Verbindung steht nicht:")
        _schreib(auskunft)
        _schreib("\nDie Angaben sind trotzdem gespeichert. Nach der Korrektur:")
        _schreib(f"  {AUFRUF} einrichten")
        e.speichern()
        return 1
    _schreib("Die Verbindung steht.")

    _schreib("\nBeide Seiten vorbereiten …")
    try:
        sync.vorbereiten(e, melde=lambda t: _schreib("  " + t))
    except RuntimeError as fehler:
        _schreib(str(fehler))
        return 1

    if not stapel:
        e.zeitplan_beim_start = _ja_nein("Beim Start des Rechners abgleichen?", e.zeitplan_beim_start)
        e.zeitplan_stuendlich = _ja_nein("Zusätzlich stündlich abgleichen?", e.zeitplan_stuendlich)

    e.speichern()
    _schreib(f"\nEinstellungen gespeichert: {paths.konfig_datei()}")

    if (e.zeitplan_beim_start or e.zeitplan_stuendlich) and (stapel or _ja_nein("Zeitplan jetzt einrichten?")):
        try:
            for zeile in schedule.einrichten(e):
                _schreib("  " + zeile)
        except schedule.ZeitplanFehler as fehler:
            _schreib(f"  Der Zeitplan ließ sich nicht einrichten: {fehler}")

    _schreib()
    _schreib("Nächster Schritt - der Grundlauf bringt beide Seiten in Einklang:")
    _schreib(f"  {AUFRUF} grundlauf --probelauf     # erst nur anzeigen")
    _schreib(f"  {AUFRUF} grundlauf                 # dann wirklich")
    return 0


def befehl_pruefen(args: argparse.Namespace) -> int:
    e = konfig_modul.laden()
    try:
        e.pruefe()
    except KonfigFehler as fehler:
        _schreib(str(fehler))
        return 2

    _schreib(f"rclone:   {rclone.finde_rclone()}")
    _schreib("Version:  " + ".".join(str(z) for z in rclone.version()))
    rclone.schreibe_rclone_konfig(e)

    ordner = e.lokal_pfad
    _schreib(f"Örtlich:  {ordner}  " + ("vorhanden" if ordner.is_dir() else "FEHLT"))
    if e.zugriffspruefung:
        da = (ordner / e.pruefdatei).exists()
        _schreib(f"Prüfdatei: {e.pruefdatei}  " + ("vorhanden" if da else "FEHLT"))

    steht, auskunft = rclone.pruefe_verbindung(e)
    _schreib(f"Fern:     {e.fernziel}  " + ("erreichbar" if steht else "NICHT erreichbar"))
    if not steht:
        _schreib(auskunft)
        return 1

    sperren = lock.liste(e)
    if sperren:
        _schreib("Sperren auf der Box:")
        for s in sperren:
            _schreib(f"  {s['name']}  seit {int(s['alter_minuten'])} Minuten")
    else:
        _schreib("Sperren:  keine")
    return 0


def _laufen_lassen(grundlauf: bool, probelauf: bool, still: bool) -> int:
    try:
        e = konfig_modul.laden()
        e.pruefe()
    except KonfigFehler as fehler:
        if not still:
            _schreib(str(fehler))
            _schreib(f"Einrichten mit: {AUFRUF} einrichten")
        return 2

    if not grundlauf and sync.braucht_grundlauf(e):
        hinweis = (
            "Der Grundlauf steht noch aus. Er bringt beide Seiten einmalig in "
            f"Einklang:\n  {AUFRUF} grundlauf"
        )
        if not still:
            _schreib(hinweis)
        return 3

    melder = None if still else _schreib
    try:
        ergebnis = sync.abgleichen(e, grundlauf=grundlauf, probelauf=probelauf, melde=melder)
    except (rclone.RcloneFehlt, rclone.RcloneZuAlt) as fehler:
        if not still:
            _schreib(str(fehler))
        return 4

    if not still:
        _schreib()
        if ergebnis.uebersprungen:
            _schreib("Übersprungen: " + ergebnis.meldung)
        elif ergebnis.gelungen:
            _schreib(f"Fertig in {int(ergebnis.dauer)} Sekunden.")
            if probelauf:
                _schreib("Das war ein Probelauf - es wurde nichts verändert.")
        else:
            _schreib(f"Mit Fehler beendet (Rückgabewert {ergebnis.rueckgabe}).")
        if ergebnis.protokoll:
            _schreib(f"Protokoll: {ergebnis.protokoll}")
    return ergebnis.rueckgabe


def befehl_grundlauf(args: argparse.Namespace) -> int:
    if not args.probelauf and not args.ohne_rueckfrage:
        _schreib("Der Grundlauf vergleicht beide Seiten und bringt sie in Einklang.")
        _schreib("Bei Dateien, die es auf beiden Seiten gibt, gewinnt die neuere.")
        _schreib("Gelöscht wird dabei nichts.")
        if not _ja_nein("Jetzt starten?", False):
            return 0
    return _laufen_lassen(grundlauf=True, probelauf=args.probelauf, still=args.still)


def befehl_abgleich(args: argparse.Namespace) -> int:
    return _laufen_lassen(grundlauf=False, probelauf=args.probelauf, still=args.still)


def befehl_status(args: argparse.Namespace) -> int:
    z = state.ermittle()
    _schreib(f"Zustand:  {z.stufe}")
    _schreib(f"Kurz:     {z.kurz}")
    for zeile in z.lang:
        _schreib(f"          {zeile}")
    if z.ordner:
        _schreib(f"Ordner:   {z.ordner}")
    if z.protokoll:
        _schreib(f"Protokoll: {z.protokoll}")
    aktiv, text = schedule.zustand()
    _schreib(f"Zeitplan: {'aktiv' if aktiv else 'keiner'}")
    if args.ausfuehrlich:
        _schreib(text)
    return 0 if z.stufe in ("gut", "laeuft") else 1


def befehl_protokoll(args: argparse.Namespace) -> int:
    dateien = state.protokolle(args.anzahl)
    if not dateien:
        _schreib("Es liegt noch kein Protokoll vor.")
        return 1
    if args.liste:
        for datei in dateien:
            _schreib(f"{datei.name}  ({datei.stat().st_size // 1024} kB)")
        return 0
    _schreib(dateien[0].read_text(encoding="utf-8", errors="replace"))
    return 0


def befehl_zeitplan(args: argparse.Namespace) -> int:
    if args.was == "aus":
        for zeile in schedule.entfernen():
            _schreib(zeile)
        return 0
    if args.was == "status":
        aktiv, text = schedule.zustand()
        _schreib("aktiv" if aktiv else "keiner")
        _schreib(text)
        return 0

    e = konfig_modul.laden()
    try:
        e.pruefe()
    except KonfigFehler as fehler:
        _schreib(str(fehler))
        return 2
    try:
        for zeile in schedule.einrichten(e):
            _schreib(zeile)
    except schedule.ZeitplanFehler as fehler:
        _schreib(str(fehler))
        return 1
    return 0


def befehl_sperren(args: argparse.Namespace) -> int:
    e = konfig_modul.laden()
    try:
        e.pruefe()
    except KonfigFehler as fehler:
        _schreib(str(fehler))
        return 2
    if args.loesen:
        anzahl = lock.alle_eigenen_loesen(e)
        _schreib(f"{anzahl} eigene Sperre(n) entfernt.")
        return 0
    sperren = lock.liste(e)
    if not sperren:
        _schreib("Keine Sperre auf der Box.")
        return 0
    for s in sperren:
        eigen = " (dieser Rechner)" if s["name"] == lock.eigener_name(e) else ""
        _schreib(f"{s['name']}  seit {int(s['alter_minuten'])} Minuten{eigen}")
    return 0


def befehl_info(args: argparse.Namespace) -> int:
    _schreib(f"storage-box-sync {__version__}")
    _schreib(f"Python          {sys.version.split()[0]} auf {sys.platform}")
    try:
        _schreib(f"rclone          {'.'.join(str(z) for z in rclone.version())}"
                 f"  ({rclone.finde_rclone()})")
    except rclone.RcloneFehlt:
        _schreib("rclone          nicht gefunden")
    _schreib(f"Einstellungen   {paths.konfig_datei()}")
    _schreib(f"Ausnahmen       {paths.filter_datei()}")
    _schreib(f"Dateilisten     {paths.arbeits_ordner()}")
    _schreib(f"Protokolle      {paths.protokoll_ordner()}")
    _schreib("Zeitplanbefehl  " + " ".join(schedule.befehl_fuer_zeitplan()))
    return 0


def befehl_ordner(args: argparse.Namespace) -> int:
    e = konfig_modul.laden()
    ordner = str(e.lokal_pfad)
    if sys.platform == "win32":
        os.startfile(ordner)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", ordner])
    else:
        subprocess.Popen(["xdg-open", ordner],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 0


def befehl_fenster(args: argparse.Namespace) -> int:
    from .gui import starte_fenster
    return starte_fenster()


def befehl_symbol(args: argparse.Namespace) -> int:
    from .gui import starte_symbol
    return starte_symbol()


# ----------------------------------------------------------------------

def baue_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=AUFRUF,
        description="Hält einen Ordner und eine Hetzner Storage Box in beide "
                    "Richtungen abgeglichen - auch über mehrere Rechner.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""Übliche Reihenfolge:
  {AUFRUF} einrichten
  {AUFRUF} grundlauf --probelauf
  {AUFRUF} grundlauf
  {AUFRUF} status
""",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    unter = p.add_subparsers(dest="befehl", metavar="BEFEHL")

    s = unter.add_parser("einrichten", help="Zugang, Ordner und Zeitplan festlegen")
    s.add_argument("--lokal", help="örtlicher Ordner")
    s.add_argument("--host", help="Server, z. B. uXXXXX.your-storagebox.de")
    s.add_argument("--benutzer", help="Benutzer der Storage Box")
    s.add_argument("--port", help="22 oder 23")
    s.add_argument("--fern", help="Ordner auf der Box, z. B. /daten")
    s.add_argument("--rechnername", help="Name dieses Rechners für Sperren und Konflikte")
    s.add_argument("--passwort-von-stdin", action="store_true",
                   help="Passwort aus der Standardeingabe lesen")
    s.add_argument("--ohne-fragen", action="store_true",
                   help="nichts nachfragen, nur die übergebenen Werte verwenden")
    s.set_defaults(funktion=befehl_einrichten)

    s = unter.add_parser("pruefen", help="Verbindung, Ordner und Prüfdatei ansehen")
    s.set_defaults(funktion=befehl_pruefen)

    s = unter.add_parser("grundlauf", help="erster Abgleich: beide Seiten in Einklang bringen")
    s.add_argument("--probelauf", action="store_true", help="nur anzeigen, nichts verändern")
    s.add_argument("--still", action="store_true", help="keine Ausgabe, nur Protokoll")
    s.add_argument("--ohne-rueckfrage", action="store_true", help="nicht nachfragen")
    s.set_defaults(funktion=befehl_grundlauf)

    s = unter.add_parser("abgleich", help="Änderungen in beide Richtungen übertragen")
    s.add_argument("--probelauf", action="store_true", help="nur anzeigen, nichts verändern")
    s.add_argument("--still", action="store_true", help="keine Ausgabe, nur Protokoll")
    s.set_defaults(funktion=befehl_abgleich)

    s = unter.add_parser("status", help="Zustand in Kurzform")
    s.add_argument("--ausfuehrlich", action="store_true", help="auch den Zeitplan im Klartext")
    s.set_defaults(funktion=befehl_status)

    s = unter.add_parser("protokoll", help="letztes Protokoll anzeigen")
    s.add_argument("--liste", action="store_true", help="nur die Dateinamen auflisten")
    s.add_argument("--anzahl", type=int, default=15, help="wie viele auflisten")
    s.set_defaults(funktion=befehl_protokoll)

    s = unter.add_parser("zeitplan", help="automatischen Lauf ein- oder ausschalten")
    s.add_argument("was", choices=["ein", "aus", "status"], nargs="?", default="status")
    s.set_defaults(funktion=befehl_zeitplan)

    s = unter.add_parser("sperren", help="Sperren auf der Box ansehen oder lösen")
    s.add_argument("--loesen", action="store_true", help="eigene Sperre entfernen")
    s.set_defaults(funktion=befehl_sperren)

    s = unter.add_parser("ordner", help="den örtlichen Ordner im Dateimanager öffnen")
    s.set_defaults(funktion=befehl_ordner)

    s = unter.add_parser("fenster", help="Einstellungsfenster öffnen")
    s.set_defaults(funktion=befehl_fenster)

    s = unter.add_parser("symbol", help="Statussymbol in der Kontrollleiste starten")
    s.set_defaults(funktion=befehl_symbol)

    s = unter.add_parser("info", help="Pfade und Versionen")
    s.set_defaults(funktion=befehl_info)

    return p


def nur_fenster(argv: list[str] | None = None) -> int:
    """Einsprungpunkt ohne Konsolenfenster: öffnet gleich die Oberfläche."""
    from .gui import starte_fenster
    return starte_fenster()


def nur_symbol(argv: list[str] | None = None) -> int:
    """Einsprungpunkt ohne Konsolenfenster: startet gleich das Symbol."""
    from .gui import starte_symbol
    return starte_symbol()


def main(argv: list[str] | None = None) -> int:
    parser = baue_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "funktion", None):
        # Ohne Befehl: Fenster öffnen, wenn möglich, sonst Hilfe
        if konfig_modul.ist_eingerichtet():
            return befehl_status(argparse.Namespace(ausfuehrlich=False))
        parser.print_help()
        return 0
    try:
        return args.funktion(args)
    except KeyboardInterrupt:
        _schreib("\nAbgebrochen.")
        return 130
    except (rclone.RcloneFehlt, rclone.RcloneZuAlt) as fehler:
        _schreib(str(fehler))
        return 4
    except KonfigFehler as fehler:
        _schreib(str(fehler))
        return 2
