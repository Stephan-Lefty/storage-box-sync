# TODO

## Sofort

- [ ] Erster Lauf gegen die echte Box:
  ```
  pamac install rclone python-pyqt6
  pipx install --system-site-packages ~/Github/storage-box-sync
  storage-box-sync einrichten
  storage-box-sync pruefen
  storage-box-sync grundlauf --probelauf    # UNBEDINGT zuerst ansehen
  storage-box-sync grundlauf
  ```
- [ ] Autostart des Symbols einrichten:
  `cp packaging/storage-box-sync-symbol.desktop ~/.config/autostart/`
- [ ] Altes Bash-Werkzeug entfernen: `~/.local/bin/storagebox-sync`
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
