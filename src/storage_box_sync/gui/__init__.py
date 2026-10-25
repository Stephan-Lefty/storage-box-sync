"""Oberfläche: Einstellungsfenster und Symbol in der Kontrollleiste.

PyQt6 ist eine freiwillige Zutat. Fehlt es, bleibt die Kommandozeile
vollständig nutzbar.
"""

from __future__ import annotations

import sys

HINWEIS = (
    "Für die Oberfläche wird PyQt6 gebraucht.\n\n"
    "  pip install \"storage-box-sync[fenster]\"\n"
    "oder über die Paketverwaltung:\n"
    "  pamac install python-pyqt6        (Manjaro, Arch)\n"
    "  sudo apt install python3-pyqt6    (Debian, Ubuntu)"
)


def _pyqt_da() -> bool:
    try:
        import PyQt6.QtWidgets  # noqa: F401
    except ImportError:
        return False
    return True


def starte_fenster() -> int:
    if not _pyqt_da():
        print(HINWEIS, file=sys.stderr)
        return 4
    from .fenster import starte
    return starte()


def starte_symbol() -> int:
    if not _pyqt_da():
        print(HINWEIS, file=sys.stderr)
        return 4
    from .symbol import starte
    return starte()
