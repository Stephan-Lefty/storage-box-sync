import subprocess
import sys

import pytest


@pytest.fixture
def aufrufe(monkeypatch):
    mitschrift = []

    def gefaelscht(*args):
        mitschrift.append(list(args))
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout="", stderr="")

    from storage_box_sync import schedule
    monkeypatch.setattr(schedule, "_lauf", gefaelscht)
    return mitschrift


@pytest.mark.skipif(sys.platform == "win32", reason="systemd gibt es nur unter Linux")
def test_systemd_einheiten_werden_geschrieben(einstellungen, aufrufe, eigene_ablage):
    from storage_box_sync import schedule

    meldungen = schedule.einrichten(einstellungen)
    ordner = schedule._systemd_ordner()
    dienst = (ordner / "storage-box-sync.service").read_text(encoding="utf-8")
    timer = (ordner / "storage-box-sync.timer").read_text(encoding="utf-8")

    assert f"RequiresMountsFor={einstellungen.lokal_pfad}" in dienst
    assert f"ConditionPathIsDirectory={einstellungen.lokal_pfad}" in dienst
    assert "Type=oneshot" in dienst
    assert "abgleich" in dienst and "--still" in dienst

    assert "OnBootSec=3min" in timer
    assert "OnUnitActiveSec=1h" in timer
    assert "Persistent=true" in timer

    assert any("enable" in a for a in aufrufe)
    assert any("Zeitplan" in m for m in meldungen)


@pytest.mark.skipif(sys.platform == "win32", reason="systemd gibt es nur unter Linux")
def test_nur_stuendlich_ohne_startausloeser(einstellungen, aufrufe, eigene_ablage):
    from storage_box_sync import schedule

    einstellungen.zeitplan_beim_start = False
    schedule.einrichten(einstellungen)
    timer = (schedule._systemd_ordner() / "storage-box-sync.timer").read_text(encoding="utf-8")
    assert "OnBootSec" not in timer
    assert "OnUnitActiveSec=1h" in timer


@pytest.mark.skipif(sys.platform == "win32", reason="systemd gibt es nur unter Linux")
def test_entfernen_raeumt_auf(einstellungen, aufrufe, eigene_ablage):
    from storage_box_sync import schedule

    schedule.einrichten(einstellungen)
    schedule.entfernen()
    ordner = schedule._systemd_ordner()
    assert not (ordner / "storage-box-sync.timer").exists()
    assert not (ordner / "storage-box-sync.service").exists()


def test_windows_aufgaben(einstellungen, aufrufe, monkeypatch):
    from storage_box_sync import schedule

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        schedule, "befehl_fuer_zeitplan",
        lambda fenster=False: [r"C:\Python\pythonw.exe", "-m", "storage_box_sync",
                               "abgleich", "--still"],
    )
    meldungen = schedule.einrichten(einstellungen)

    angelegt = [a for a in aufrufe if "/Create" in a]
    assert len(angelegt) == 2
    namen = [a[a.index("/TN") + 1] for a in angelegt]
    assert schedule.WIN_AUFGABE_START in namen
    assert schedule.WIN_AUFGABE_STUNDE in namen
    for a in angelegt:
        assert "abgleich --still" in a[a.index("/TR") + 1]
        assert "/IT" in a
    assert len(meldungen) == 2


def test_windows_aufgaben_entfernen(einstellungen, aufrufe, monkeypatch):
    from storage_box_sync import schedule

    monkeypatch.setattr(sys, "platform", "win32")
    schedule.entfernen()
    assert len([a for a in aufrufe if "/Delete" in a]) == 2


def test_zeitplanbefehl_ist_absolut_oder_modul():
    from storage_box_sync import schedule

    befehl = schedule.befehl_fuer_zeitplan()
    assert befehl[-2:] == ["abgleich", "--still"]
    assert befehl[0]
