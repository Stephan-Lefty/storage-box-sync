"""rclone finden, einrichten und aufrufen."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import paths
from .config import Einstellungen

MINDESTVERSION = (1, 66)   # ab hier gibt es --conflict-resolve und --conflict-loser
RESYNC_MODUS_AB = (1, 67)  # ab hier gibt es --resync-mode


class RcloneFehlt(Exception):
    """rclone ist nicht auffindbar."""

    def __str__(self) -> str:
        if sys.platform == "win32":
            hinweis = (
                "rclone wurde nicht gefunden.\n\n"
                "Installation unter Windows, eines davon:\n"
                "  winget install Rclone.Rclone\n"
                "  scoop install rclone\n"
                "  oder von https://rclone.org/downloads/ herunterladen und\n"
                "  rclone.exe in einen Ordner im Suchpfad legen."
            )
        elif sys.platform == "darwin":
            hinweis = "rclone wurde nicht gefunden.\n\n  brew install rclone"
        else:
            hinweis = (
                "rclone wurde nicht gefunden.\n\n"
                "Installation unter Linux, je nach System:\n"
                "  pamac install rclone        (Manjaro, Arch)\n"
                "  sudo apt install rclone     (Debian, Ubuntu)\n"
                "  sudo dnf install rclone     (Fedora)"
            )
        return hinweis


class RcloneZuAlt(Exception):
    def __init__(self, gefunden: tuple[int, ...]):
        self.gefunden = gefunden
        super().__init__(
            "rclone {} ist zu alt. Für den Zweiweg-Abgleich wird mindestens "
            "{} gebraucht.".format(
                ".".join(str(z) for z in gefunden),
                ".".join(str(z) for z in MINDESTVERSION),
            )
        )


def _windows_orte() -> list[Path]:
    orte: list[Path] = []
    for umgebung in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA", "USERPROFILE"):
        basis = os.environ.get(umgebung)
        if not basis:
            continue
        orte += [
            Path(basis) / "rclone" / "rclone.exe",
            Path(basis) / "Programs" / "rclone" / "rclone.exe",
            Path(basis) / "scoop" / "shims" / "rclone.exe",
        ]
    orte.append(Path("C:/ProgramData/chocolatey/bin/rclone.exe"))
    return orte


def finde_rclone() -> Path:
    eigen = os.environ.get("STORAGE_BOX_SYNC_RCLONE")
    if eigen and Path(eigen).exists():
        return Path(eigen)

    gefunden = shutil.which("rclone")
    if gefunden:
        return Path(gefunden)

    kandidaten = _windows_orte() if sys.platform == "win32" else [
        Path("/usr/bin/rclone"),
        Path("/usr/local/bin/rclone"),
        Path("/opt/homebrew/bin/rclone"),
        Path.home() / ".local" / "bin" / "rclone",
    ]
    for pfad in kandidaten:
        if pfad.exists():
            return pfad
    raise RcloneFehlt()


def startoptionen() -> dict:
    """Unter Windows kein Konsolenfenster aufblitzen lassen."""
    if sys.platform != "win32":
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"startupinfo": info, "creationflags": subprocess.CREATE_NO_WINDOW}


def lauf(
    *args: str,
    mit_konfig: bool = True,
    zeitgrenze: int | None = 120,
    eingabe: str | None = None,
) -> subprocess.CompletedProcess:
    befehl = [str(finde_rclone())]
    if mit_konfig:
        befehl += ["--config", str(paths.rclone_konfig_datei())]
    befehl += [str(a) for a in args]
    return subprocess.run(
        befehl,
        capture_output=True,
        text=True,
        input=eingabe,
        timeout=zeitgrenze,
        **startoptionen(),
    )


def version() -> tuple[int, ...]:
    ergebnis = lauf("version", mit_konfig=False, zeitgrenze=30)
    treffer = re.search(r"rclone\s+v?(\d+)\.(\d+)(?:\.(\d+))?", ergebnis.stdout or "")
    if not treffer:
        return (0, 0, 0)
    return tuple(int(t) for t in treffer.groups(default="0"))


def pruefe_version() -> tuple[int, ...]:
    gefunden = version()
    if gefunden < MINDESTVERSION:
        raise RcloneZuAlt(gefunden)
    return gefunden


def kann_resync_modus() -> bool:
    return version() >= RESYNC_MODUS_AB


def verschleiere(passwort: str) -> str:
    """Passwort in die Form bringen, die rclone in seiner Konfiguration erwartet."""
    ergebnis = lauf("obscure", passwort, mit_konfig=False, zeitgrenze=30)
    if ergebnis.returncode != 0:
        raise RuntimeError(f"rclone obscure ist fehlgeschlagen: {ergebnis.stderr.strip()}")
    return ergebnis.stdout.strip()


def schreibe_rclone_konfig(e: Einstellungen) -> Path:
    """Eigene rclone-Konfiguration anlegen - die des Benutzers bleibt unberührt."""
    paths.lege_ordner_an()
    zeilen = [
        "# von storage-box-sync erzeugt - nicht von Hand ändern",
        f"[{e.remote_name}]",
        "type = sftp",
        f"host = {e.host}",
        f"user = {e.benutzer}",
        f"port = {e.port}",
        "shell_type = unix",
        "md5sum_command = md5 -r",
        "sha1sum_command = sha1 -r",
    ]
    if e.schluesseldatei:
        zeilen.append(f"key_file = {e.schluesseldatei}")
    else:
        zeilen.append(f"pass = {e.passwort}")

    datei = paths.rclone_konfig_datei()
    datei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    if sys.platform != "win32":
        try:
            datei.chmod(0o600)
        except OSError:
            pass
    return datei


def pruefe_verbindung(e: Einstellungen) -> tuple[bool, str]:
    """Kurzer Blick auf die Box: erreichbar und Pfad vorhanden?"""
    ergebnis = lauf("lsd", e.fernziel, "--max-depth", "1", zeitgrenze=60)
    if ergebnis.returncode == 0:
        return True, (ergebnis.stdout or "").strip() or "Verbindung steht, der Ordner ist leer."
    return False, (ergebnis.stderr or ergebnis.stdout or "Unbekannter Fehler").strip()


# ----------------------------------------------------------------------
#  Schalter der vorhandenen rclone-Fassung
# ----------------------------------------------------------------------

_SCHALTER: set[str] | None = None


def bekannte_schalter(neu_einlesen: bool = False) -> set[str]:
    """Alle Schalter, die diese rclone-Fassung kennt.

    Damit lässt sich vor dem Lauf prüfen, ob ein Schalter fehlt - sonst
    bricht rclone mit einer englischen Meldung ab, die niemandem weiterhilft.
    """
    global _SCHALTER
    if _SCHALTER is not None and not neu_einlesen:
        return _SCHALTER

    text = ""
    for args in (("bisync", "--help"), ("help", "flags")):
        try:
            ergebnis = lauf(*args, mit_konfig=False, zeitgrenze=30)
        except (RcloneFehlt, OSError, subprocess.SubprocessError):
            continue
        text += (ergebnis.stdout or "") + (ergebnis.stderr or "")

    _SCHALTER = set(re.findall(r"--[a-zA-Z0-9][a-zA-Z0-9-]+", text))
    return _SCHALTER


def unbekannte_schalter(befehl: list[str]) -> list[str]:
    bekannt = bekannte_schalter()
    if not bekannt:
        return []        # konnte nicht ermittelt werden - dann nicht meckern
    return [t for t in befehl if t.startswith("--") and t not in bekannt]
