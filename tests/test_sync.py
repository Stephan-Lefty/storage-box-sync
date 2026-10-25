import json
import os
import stat
import sys
from pathlib import Path

import pytest

ATTRAPPE = Path(__file__).parent / "attrappen" / "rclone_attrappe.py"


@pytest.fixture
def attrappe(tmp_path, monkeypatch):
    """Ein ausführbares Hüllskript, das als rclone auftritt."""
    if sys.platform == "win32":
        pytest.skip("Hüllskript nur unter POSIX")
    huelle = tmp_path / "rclone"
    huelle.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{ATTRAPPE}" "$@"\n', encoding="utf-8")
    huelle.chmod(huelle.stat().st_mode | stat.S_IEXEC)

    mitschrift = tmp_path / "aufrufe.jsonl"
    monkeypatch.setenv("STORAGE_BOX_SYNC_RCLONE", str(huelle))
    monkeypatch.setenv("ATTRAPPE_MITSCHRIFT", str(mitschrift))
    return mitschrift


def _aufrufe(mitschrift: Path) -> list[list[str]]:
    if not mitschrift.exists():
        return []
    return [json.loads(z) for z in mitschrift.read_text(encoding="utf-8").splitlines() if z]


def _unterbefehl(args: list[str]) -> str:
    """Den rclone-Unterbefehl aus einem mitgeschriebenen Aufruf ziehen."""
    rest = list(args)
    if rest[:1] == ["--config"]:
        rest = rest[2:]
    return rest[0] if rest else ""


def _hat(aufrufe, unterbefehl, enthaelt=None):
    for args in aufrufe:
        if _unterbefehl(args) != unterbefehl:
            continue
        if enthaelt is None or enthaelt in args:
            return True
    return False


# ----------------------------------------------------------------------

def test_befehl_enthaelt_die_schutzvorkehrungen(einstellungen, monkeypatch):
    from storage_box_sync import rclone, sync

    monkeypatch.setattr(rclone, "kann_resync_modus", lambda: True)
    befehl = sync.baue_befehl(einstellungen, grundlauf=False, probelauf=False)

    assert befehl[0] == "bisync"
    assert "--check-access" in befehl
    assert befehl[befehl.index("--check-filename") + 1] == "RCLONE_TEST"
    assert befehl[befehl.index("--max-delete") + 1] == "50"
    assert "--resilient" in befehl and "--recover" in befehl
    assert befehl[befehl.index("--conflict-resolve") + 1] == "newer"
    assert befehl[befehl.index("--conflict-loser") + 1] == "pathname"
    assert "pruefrechner" in befehl[befehl.index("--conflict-suffix") + 1]
    assert "--resync" not in befehl
    assert "--dry-run" not in befehl


def test_grundlauf_und_probelauf_im_befehl(einstellungen, monkeypatch):
    from storage_box_sync import rclone, sync

    monkeypatch.setattr(rclone, "kann_resync_modus", lambda: True)
    befehl = sync.baue_befehl(einstellungen, grundlauf=True, probelauf=True)
    assert "--resync" in befehl
    assert befehl[befehl.index("--resync-mode") + 1] == "newer"
    assert "--dry-run" in befehl


def test_alte_rclone_fassung_ohne_resync_modus(einstellungen, monkeypatch):
    from storage_box_sync import rclone, sync

    monkeypatch.setattr(rclone, "kann_resync_modus", lambda: False)
    befehl = sync.baue_befehl(einstellungen, grundlauf=True, probelauf=False)
    assert "--resync" in befehl
    assert "--resync-mode" not in befehl


def test_ohne_konfliktregel_keine_konfliktschalter(einstellungen, monkeypatch):
    from storage_box_sync import rclone, sync

    monkeypatch.setattr(rclone, "kann_resync_modus", lambda: True)
    einstellungen.konflikt_regel = "none"
    befehl = sync.baue_befehl(einstellungen, grundlauf=False, probelauf=False)
    assert "--conflict-resolve" not in befehl


def test_fehlende_pruefdatei_bricht_ab_ohne_rclone(einstellungen, attrappe):
    from storage_box_sync import sync

    einstellungen.grundlauf_erledigt = True
    ergebnis = sync.abgleichen(einstellungen)
    assert ergebnis.rueckgabe == 10
    assert "Prüfdatei" in ergebnis.meldung
    assert not _hat(_aufrufe(attrappe), "bisync")


def test_nicht_eingehaengtes_laufwerk_bricht_ab(einstellungen, attrappe, eigene_ablage):
    from storage_box_sync import sync

    einstellungen.lokal = str(eigene_ablage / "nicht-eingehaengt")
    einstellungen.grundlauf_erledigt = True
    ergebnis = sync.abgleichen(einstellungen)
    assert ergebnis.rueckgabe == 10
    assert "eingehängt" in ergebnis.meldung


def test_vollstaendiger_grundlauf_mit_attrappe(einstellungen, attrappe):
    from storage_box_sync import config, sync

    (einstellungen.lokal_pfad / einstellungen.pruefdatei).write_text("x")
    config.schreibe_ausnahmen(einstellungen)

    ergebnis = sync.abgleichen(einstellungen, grundlauf=True)
    assert ergebnis.gelungen
    assert ergebnis.protokoll and ergebnis.protokoll.exists()
    protokoll = ergebnis.protokoll.read_text(encoding="utf-8")
    assert "Bisync erfolgreich" in protokoll
    assert "pruefrechner" in protokoll

    aufrufe = _aufrufe(attrappe)
    assert _hat(aufrufe, "bisync", "--resync")
    # Sperre geholt und wieder freigegeben
    assert _hat(aufrufe, "rcat")
    assert _hat(aufrufe, "deletefile")

    # Grundlauf ist nun vermerkt
    assert config.laden().grundlauf_erledigt is True


def test_fehlerhafter_lauf_wird_vermerkt(einstellungen, attrappe, monkeypatch):
    from storage_box_sync import state, sync

    (einstellungen.lokal_pfad / einstellungen.pruefdatei).write_text("x")
    einstellungen.grundlauf_erledigt = True
    monkeypatch.setenv("ATTRAPPE_BISYNC_CODE", "7")

    ergebnis = sync.abgleichen(einstellungen)
    assert ergebnis.rueckgabe == 7
    assert not ergebnis.gelungen
    assert state.lies_lauf()["rueckgabe"] == 7
    assert state.ermittle(einstellungen).stufe == "fehler"


def test_zu_alte_rclone_fassung_wird_abgelehnt(einstellungen, attrappe, monkeypatch):
    from storage_box_sync import rclone, sync

    (einstellungen.lokal_pfad / einstellungen.pruefdatei).write_text("x")
    monkeypatch.setenv("ATTRAPPE_VERSION", "1.62.0")
    with pytest.raises(rclone.RcloneZuAlt):
        sync.abgleichen(einstellungen, grundlauf=True)


def test_vorbereiten_legt_pruefdateien_an(einstellungen, attrappe):
    from storage_box_sync import sync

    sync.vorbereiten(einstellungen)
    assert (einstellungen.lokal_pfad / einstellungen.pruefdatei).exists()
    aufrufe = _aufrufe(attrappe)
    assert _hat(aufrufe, "mkdir")
    assert _hat(aufrufe, "copy")


def test_sperre_eines_anderen_rechners_ueberspringt(einstellungen, attrappe, monkeypatch):
    import json as _json
    from datetime import datetime, timedelta, timezone

    from storage_box_sync import sync

    (einstellungen.lokal_pfad / einstellungen.pruefdatei).write_text("x")
    einstellungen.grundlauf_erledigt = True

    zeit = datetime.now(timezone.utc) - timedelta(minutes=2)
    monkeypatch.setenv("ATTRAPPE_LSJSON", _json.dumps([{
        "Name": "anderer-pc.json", "IsDir": False,
        "ModTime": zeit.isoformat().replace("+00:00", "Z"),
    }]))

    ergebnis = sync.abgleichen(einstellungen)
    assert ergebnis.uebersprungen is True
    assert "anderer-pc" in ergebnis.meldung
    assert not _hat(_aufrufe(attrappe), "bisync")


def test_alle_benutzten_schalter_kennt_rclone(einstellungen, attrappe, monkeypatch):
    """Die Attrappe gibt die Schalterliste von rclone 1.67 aus - passt unser
    Befehl dazu, stimmen die Namen."""
    from storage_box_sync import rclone, sync

    rclone.bekannte_schalter(neu_einlesen=True)
    for grundlauf in (True, False):
        for probelauf in (True, False):
            befehl = sync.baue_befehl(einstellungen, grundlauf, probelauf)
            assert rclone.unbekannte_schalter(befehl) == []


def test_unbekannter_schalter_bricht_mit_klarer_meldung_ab(einstellungen, attrappe, monkeypatch):
    from storage_box_sync import rclone, sync

    (einstellungen.lokal_pfad / einstellungen.pruefdatei).write_text("x")
    einstellungen.grundlauf_erledigt = True
    monkeypatch.setattr(rclone, "bekannte_schalter", lambda neu_einlesen=False: {"--dry-run"})

    ergebnis = sync.abgleichen(einstellungen)
    assert ergebnis.rueckgabe == 11
    assert "kennt folgende Schalter nicht" in ergebnis.meldung
    assert not _hat(_aufrufe(attrappe), "bisync")
