"""StatusNotifierItem – Tray-Symbol direkt über D-Bus (KDE Plasma 6 Wayland).

DBusGMainLoop muss im Haupt-Thread vor QApplication gesetzt werden.
Qt auf Linux nutzt GLib als Event-Loop-Unterbau, daher kein eigener Thread nötig.
"""

from __future__ import annotations

import os
from typing import Callable

import dbus
import dbus.mainloop.glib
import dbus.service

_SNI_IFACE = "org.kde.StatusNotifierItem"
_SNI_PATH = "/StatusNotifierItem"
_WATCHER_SVC = "org.kde.StatusNotifierWatcher"
_WATCHER_PATH = "/StatusNotifierWatcher"
_WATCHER_IFACE = "org.kde.StatusNotifierWatcher"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"


class StatusNotifierItem(dbus.service.Object):
    """Tray-Symbol über StatusNotifierItem D-Bus-Protokoll."""

    def __init__(
        self,
        on_activate: Callable[[], None],
        on_context: Callable[[int, int], None],
    ) -> None:
        self._on_activate = on_activate
        self._on_context = on_context
        self._icon = "folder-cloud"
        self._tooltip = "Storage Box"
        self._status = "Active"

        # GLib-Mainloop an den Bus binden, ohne Qt's eigenen Loop zu stören
        _ml = dbus.mainloop.glib.DBusGMainLoop()
        bus = dbus.SessionBus(mainloop=_ml)
        svc = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        bus_name = dbus.service.BusName(svc, bus)
        super().__init__(bus_name, _SNI_PATH)

        try:
            watcher = bus.get_object(_WATCHER_SVC, _WATCHER_PATH)
            watcher.RegisterStatusNotifierItem(svc, dbus_interface=_WATCHER_IFACE)
            print(f"[SNI] Registriert als {svc}", flush=True)
        except dbus.DBusException as exc:
            print(f"[SNI] Watcher-Registrierung fehlgeschlagen: {exc}", flush=True)

    # ── Signale ─────────────────────────────────────────────────────────

    @dbus.service.signal(_SNI_IFACE)
    def NewIcon(self) -> None: ...

    @dbus.service.signal(_SNI_IFACE)
    def NewStatus(self, status: str) -> None: ...

    @dbus.service.signal(_SNI_IFACE)
    def NewToolTip(self) -> None: ...

    # ── Methoden ────────────────────────────────────────────────────────

    @dbus.service.method(_SNI_IFACE, in_signature="ii")
    def Activate(self, x: int, y: int) -> None:
        self._on_activate()

    @dbus.service.method(_SNI_IFACE, in_signature="ii")
    def SecondaryActivate(self, x: int, y: int) -> None:
        pass

    @dbus.service.method(_SNI_IFACE, in_signature="ii")
    def ContextMenu(self, x: int, y: int) -> None:
        self._on_context(int(x), int(y))

    @dbus.service.method(_SNI_IFACE, in_signature="is")
    def Scroll(self, delta: int, orientation: str) -> None:
        pass

    # ── Eigenschaften ───────────────────────────────────────────────────

    @dbus.service.method(_PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, iface: str, name: str):
        return self.GetAll(iface).get(name, dbus.String(""))

    @dbus.service.method(_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface: str) -> dict:
        leer = dbus.Array([], signature="(iiay)")
        return {
            "Category":            dbus.String("ApplicationStatus"),
            "Id":                  dbus.String("storage-box-sync"),
            "Title":               dbus.String("Storage Box"),
            "Status":              dbus.String(self._status),
            "IconName":            dbus.String(self._icon),
            "IconPixmap":          leer,
            "AttentionIconName":   dbus.String(""),
            "AttentionIconPixmap": leer,
            "OverlayIconName":     dbus.String(""),
            "OverlayIconPixmap":   leer,
            "ToolTip": dbus.Struct(
                (dbus.String(""), leer, dbus.String("Storage Box"), dbus.String(self._tooltip)),
                signature="sa(iiay)ss",
            ),
            "ItemIsMenu": dbus.Boolean(False),
        }

    # ── Helfer ──────────────────────────────────────────────────────────

    def aktualisiere(self, icon: str, tooltip: str) -> None:
        self._icon = icon
        self._tooltip = tooltip
        self.NewIcon()
        self.NewToolTip()
