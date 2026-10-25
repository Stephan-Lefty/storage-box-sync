import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def eigene_ablage(tmp_path, monkeypatch):
    """Konfiguration und Zustand in ein Wegwerf-Verzeichnis umleiten."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "konfig"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "zustand"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "konfig"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "zustand"))
    from storage_box_sync import paths
    paths.lege_ordner_an()
    return tmp_path


@pytest.fixture
def einstellungen(eigene_ablage):
    from storage_box_sync.config import Einstellungen
    ordner = eigene_ablage / "daten"
    ordner.mkdir()
    return Einstellungen(
        lokal=str(ordner),
        host="u123456.your-storagebox.de",
        benutzer="u123456",
        passwort="verschleiert",
        rechnername="pruefrechner",
    )
