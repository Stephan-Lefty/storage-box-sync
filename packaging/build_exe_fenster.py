"""PyInstaller-Einstieg für storage-box-sync-fenster.exe (ohne Konsolenfenster)."""
from storage_box_sync.cli import nur_fenster

if __name__ == "__main__":
    raise SystemExit(nur_fenster())
