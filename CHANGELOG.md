# Änderungen

Die Versionsnummern folgen [Semantic Versioning](https://semver.org/lang/de/).

## 0.1.0 – erste Fassung

* Zweiweg-Abgleich zwischen einem örtlichen Ordner und einer Hetzner Storage
  Box über rclone bisync und SFTP
* Prüfdatei auf beiden Seiten, Löschgrenze in Prozent und Probelauf als Schutz
  vor Datenverlust durch nicht eingehängte Laufwerke
* Konfliktbehandlung: die neuere Fassung gewinnt, die unterlegene bleibt unter
  einem sprechenden Namen erhalten
* Sperrdatei auf der Box, damit nie zwei Rechner gleichzeitig abgleichen
* Zeitplan beim Start und stündlich – systemd, Aufgabenplanung, launchd
* Einstellungsfenster und Statussymbol in der Kontrollleiste (PyQt6)
* Kommandozeile mit `einrichten`, `pruefen`, `grundlauf`, `abgleich`,
  `status`, `protokoll`, `zeitplan`, `sperren`, `ordner`, `info`
* eigene rclone-Konfiguration, damit eine vorhandene nicht angefasst wird
