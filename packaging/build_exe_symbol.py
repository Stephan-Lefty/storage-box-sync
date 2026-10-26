"""PyInstaller-Einstieg für storage-box-sync-symbol.exe (ohne Konsolenfenster)."""
from storage_box_sync.cli import nur_symbol

if __name__ == "__main__":
    raise SystemExit(nur_symbol())
