import json

import pytest


def test_pruefung_meldet_fehlende_angaben(eigene_ablage):
    from storage_box_sync.config import Einstellungen, KonfigFehler

    with pytest.raises(KonfigFehler, match="örtlicher Ordner"):
        Einstellungen().pruefe()

    with pytest.raises(KonfigFehler, match="Server"):
        Einstellungen(lokal="/tmp").pruefe()

    with pytest.raises(KonfigFehler, match="Passwort"):
        Einstellungen(lokal="/tmp", host="h", benutzer="u").pruefe()


def test_pruefung_grenzen(einstellungen):
    from storage_box_sync.config import KonfigFehler

    einstellungen.pruefe()

    einstellungen.uebertragungen = 20
    with pytest.raises(KonfigFehler, match="zehn Verbindungen"):
        einstellungen.pruefe()
    einstellungen.uebertragungen = 4

    einstellungen.max_loeschen = 0
    with pytest.raises(KonfigFehler, match="Löschgrenze"):
        einstellungen.pruefe()
    einstellungen.max_loeschen = 50

    einstellungen.konflikt_regel = "muenzwurf"
    with pytest.raises(KonfigFehler, match="Konfliktregel"):
        einstellungen.pruefe()


def test_speichern_und_laden(einstellungen):
    from storage_box_sync import config, paths

    einstellungen.konflikt_regel = "older"
    einstellungen.speichern()

    geladen = config.laden()
    assert geladen.konflikt_regel == "older"
    assert geladen.host == einstellungen.host
    assert geladen.lokal == einstellungen.lokal
    assert paths.filter_datei().exists()


def test_unbekannte_felder_werden_ignoriert(einstellungen):
    from storage_box_sync import config, paths

    einstellungen.speichern()
    datei = paths.konfig_datei()
    daten = json.loads(datei.read_text(encoding="utf-8"))
    daten["aus_einer_neueren_fassung"] = 42
    datei.write_text(json.dumps(daten), encoding="utf-8")

    geladen = config.laden()          # darf nicht stolpern
    assert geladen.host == einstellungen.host


def test_kaputte_datei_gibt_klaren_fehler(einstellungen):
    from storage_box_sync import config, paths

    einstellungen.speichern()
    paths.konfig_datei().write_text("{kein json", encoding="utf-8")
    with pytest.raises(config.KonfigFehler, match="unlesbar"):
        config.laden()


def test_ausnahmen_enthalten_den_sperrordner(einstellungen):
    from storage_box_sync import config, paths

    config.schreibe_ausnahmen(einstellungen)
    inhalt = paths.filter_datei().read_text(encoding="utf-8")
    assert ".storage-box-sync-sperren" in inhalt
    assert ".zfs" in inhalt
    assert "RCLONE_TEST" not in inhalt      # darf nie ausgenommen werden
