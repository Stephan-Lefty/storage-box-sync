# TODO

## Sofort

- [x] Erster Lauf gegen die echte Box (25.10.2026, Port 22)
- [x] Autostart des Symbols eingerichtet
- [x] Symbol erscheint in KDE Plasma 6 Wayland (SNI via dbus-python)
- [x] Altes Bash-Werkzeug entfernt
- [ ] Anwendungspasswort `dialos.org / ClaudIA` widerrufen (stand im Klartext im Chat)

## Demnächst

- [ ] Zweiter Rechner (Windows): `--rechnername windows-buero`, dann `grundlauf`
- [ ] Prüfen ob `--sftp-concurrency 2` mit bisync angenommen wird
- [ ] Verhalten von `--conflict-suffix` mit zwei Werten in der Praxis ansehen
- [ ] Geschwindigkeit und Verbindungszahl bei 17 GB über Port 23 messen

## Ideen

- Wächter, der bei Dateiänderung abgleicht (`watchdog`)
- Verschlüsseltes Passwort über `keyring` statt `rclone obscure`
- Momentaufnahmen der Storage Box aus dem Tool anstoßen
- Veröffentlichung im AUR auf Grundlage von `packaging/PKGBUILD`
