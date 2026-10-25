import stat
import sys
from pathlib import Path

import pytest

ATTRAPPE = Path(__file__).parent / "attrappen" / "rclone_attrappe.py"


@pytest.fixture
def attrappe(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("Hüllskript nur unter POSIX")
    huelle = tmp_path / "rclone"
    huelle.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{ATTRAPPE}" "$@"\n', encoding="utf-8")
    huelle.chmod(huelle.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("STORAGE_BOX_SYNC_RCLONE", str(huelle))
    monkeypatch.setenv("ATTRAPPE_MITSCHRIFT", str(tmp_path / "aufrufe.jsonl"))
    return huelle


def test_hilfe(capsys):
    from storage_box_sync.cli import main

    with pytest.raises(SystemExit) as abbruch:
        main(["--help"])
    assert abbruch.value.code == 0
    assert "Storage Box" in capsys.readouterr().out


def test_status_ohne_einrichtung(eigene_ablage, capsys):
    from storage_box_sync.cli import main

    assert main(["status"]) == 1
    assert "uneingerichtet" in capsys.readouterr().out


def test_info_nennt_die_pfade(eigene_ablage, capsys):
    from storage_box_sync.cli import main

    assert main(["info"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Einstellungen" in ausgabe
    assert "Protokolle" in ausgabe


def test_abgleich_verlangt_erst_den_grundlauf(einstellungen, attrappe, capsys):
    from storage_box_sync.cli import main

    einstellungen.speichern()
    assert main(["abgleich"]) == 3
    assert "Grundlauf" in capsys.readouterr().out


def test_einrichten_ohne_fragen(eigene_ablage, attrappe, monkeypatch, capsys):
    from storage_box_sync import config
    from storage_box_sync.cli import main

    ordner = eigene_ablage / "daten"
    ordner.mkdir()

    # Zeitplan nicht wirklich anlegen
    from storage_box_sync import schedule
    monkeypatch.setattr(schedule, "einrichten", lambda e: ["Zeitplan übersprungen (Test)"])

    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO("geheim\n"))

    rueckgabe = main([
        "einrichten", "--ohne-fragen",
        "--lokal", str(ordner),
        "--host", "u1.your-storagebox.de",
        "--benutzer", "u1",
        "--port", "23",
        "--fern", "/",
        "--passwort-von-stdin",
    ])
    e = config.laden()
    assert e.passwort == "VERSCHLEIERT"
    assert e.lokal == str(ordner)
    assert e.host == "u1.your-storagebox.de"
    assert (ordner / "RCLONE_TEST").exists()
    assert rueckgabe == 0
    assert "gespeichert" in capsys.readouterr().out.lower()


def test_protokoll_ohne_protokolle(eigene_ablage, capsys):
    from storage_box_sync.cli import main

    assert main(["protokoll"]) == 1
    assert "kein Protokoll" in capsys.readouterr().out
