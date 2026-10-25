import json
import subprocess
from datetime import datetime, timedelta, timezone


def _antwort(rueckgabe=0, aus="", fehler=""):
    return subprocess.CompletedProcess(args=["rclone"], returncode=rueckgabe,
                                       stdout=aus, stderr=fehler)


def _lsjson(namen_mit_alter):
    eintraege = []
    for name, minuten in namen_mit_alter:
        zeit = datetime.now(timezone.utc) - timedelta(minutes=minuten)
        eintraege.append({"Name": name, "IsDir": False,
                          "ModTime": zeit.isoformat().replace("+00:00", "Z")})
    return json.dumps(eintraege)


def test_eigener_name_wird_entschaerft(einstellungen):
    from storage_box_sync import lock

    einstellungen.rechnername = "Büro PC / 2"
    assert lock.eigener_name(einstellungen) == "B_ro_PC___2.json"


def test_fehlender_ordner_ist_keine_sperre(einstellungen, monkeypatch):
    from storage_box_sync import lock, rclone

    monkeypatch.setattr(rclone, "lauf", lambda *a, **k: _antwort(3, fehler="directory not found"))
    assert lock.liste(einstellungen) == []


def test_frische_fremde_sperre_haelt_auf(einstellungen, monkeypatch):
    from storage_box_sync import lock, rclone

    def gefaelscht(*args, **kwargs):
        if args and args[0] == "lsjson":
            return _antwort(0, _lsjson([("windows-pc.json", 4)]))
        return _antwort(0)

    monkeypatch.setattr(rclone, "lauf", gefaelscht)
    lage = lock.nehmen(einstellungen)
    assert lage.erhalten is False
    assert lage.inhaber == "windows-pc"
    assert "anderer Rechner" in lage.hinweis


def test_verwaiste_fremde_sperre_wird_entfernt(einstellungen, monkeypatch):
    from storage_box_sync import lock, rclone

    aufrufe = []

    def gefaelscht(*args, **kwargs):
        aufrufe.append(args)
        if args and args[0] == "lsjson":
            if len([a for a in aufrufe if a and a[0] == "lsjson"]) == 1:
                return _antwort(0, _lsjson([("windows-pc.json", 500)]))
            return _antwort(0, "[]")
        return _antwort(0)

    monkeypatch.setattr(rclone, "lauf", gefaelscht)
    monkeypatch.setattr(lock, "NACHPRUEFUNG_SEKUNDEN", 0)

    lage = lock.nehmen(einstellungen)
    assert lage.erhalten is True
    assert any(a[0] == "deletefile" for a in aufrufe if a)
    assert any(a[0] == "rcat" for a in aufrufe if a)


def test_gleichzeitiger_zugriff_der_kleinere_name_gewinnt(einstellungen, monkeypatch):
    from storage_box_sync import lock, rclone

    einstellungen.rechnername = "zweiter"
    zustand = {"runde": 0}

    def gefaelscht(*args, **kwargs):
        if args and args[0] == "lsjson":
            zustand["runde"] += 1
            if zustand["runde"] == 1:
                return _antwort(0, "[]")
            return _antwort(0, _lsjson([("erster.json", 0), ("zweiter.json", 0)]))
        return _antwort(0)

    monkeypatch.setattr(rclone, "lauf", gefaelscht)
    monkeypatch.setattr(lock, "NACHPRUEFUNG_SEKUNDEN", 0)

    lage = lock.nehmen(einstellungen)
    assert lage.erhalten is False
    assert lage.inhaber == "erster"


def test_abgeschaltete_fernsperre(einstellungen, monkeypatch):
    from storage_box_sync import lock, rclone

    einstellungen.fernsperre = False
    monkeypatch.setattr(rclone, "lauf", lambda *a, **k: _antwort(1))
    assert lock.nehmen(einstellungen).erhalten is True
