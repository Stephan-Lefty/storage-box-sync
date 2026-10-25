#!/usr/bin/env python3
"""Attrappe für rclone: schreibt alle Aufrufe mit und tut selbst nichts.

Steuerung über Umgebungsvariablen:
  ATTRAPPE_MITSCHRIFT   Datei, in die jeder Aufruf geschrieben wird
  ATTRAPPE_VERSION      Rückgabe für "rclone version" (Vorgabe 1.70.0)
  ATTRAPPE_LSJSON       Rückgabe für "rclone lsjson" (Vorgabe [])
  ATTRAPPE_BISYNC_CODE  Rückgabewert für "rclone bisync" (Vorgabe 0)
"""

import json
import os
import sys


def main() -> int:
    args = sys.argv[1:]
    mitschrift = os.environ.get("ATTRAPPE_MITSCHRIFT")
    if mitschrift:
        with open(mitschrift, "a", encoding="utf-8") as datei:
            datei.write(json.dumps(args, ensure_ascii=False) + "\n")

    ohne_konfig = [a for a in args if a not in ("--config",)]
    befehl = ""
    for teil in ohne_konfig:
        if not teil.startswith("-") and "/" not in teil and "\\" not in teil:
            befehl = teil
            break

    # Schalterliste, wie sie rclone ab 1.67 ausgibt
    if "--help" in args or befehl == "help":
        print("""Usage: rclone bisync remote1:path1 remote2:path2 [flags]

Flags:
      --check-access                 Ensure expected RCLONE_TEST files are found
      --check-filename string        Filename for --check-access (default "RCLONE_TEST")
      --check-sync string            Controls comparison of final listings (default "true")
      --compare string               Comma-separated list of bisync-specific compare options
      --conflict-loser ConflictLoserAction   Action to take on the loser of a sync conflict
      --conflict-resolve string      Automatically resolve conflicts by preferring the chosen side
      --conflict-suffix stringArray  Suffix to use when renaming a --conflict-loser
      --create-empty-src-dirs        Sync creation and deletion of empty directories
      --dry-run                      Do a trial run with no permanent changes
      --filters-file string          Read filtering patterns from a file
      --force                        Bypass --max-delete safety check
  -h, --help                         help for bisync
      --ignore-listing-checksum      Do not use checksums for listings
      --max-delete PERCENT           Safety check on maximum percentage of deleted files allowed
      --max-lock Duration            Consider lock files older than this to be expired
      --no-cleanup                   Retain working files
      --no-slow-hash                 Ignore listing checksums only on backends where they are slow
      --recover                      Automatically recover from interruptions
      --remove-empty-dirs            Remove ALL empty directories at the final cleanup step
      --resilient                    Allow future runs to retry after certain less-serious errors
      --resync                       Performs the resync run
      --resync-mode string           During resync, prefer the version that is chosen
      --slow-hash-sync-only          Ignore slow checksums for listings and deltas
      --workdir string               Use custom working directory

Global Flags:
      --checkers int                 Number of checkers to run in parallel
      --config string                Config file
      --contimeout Duration          Connect timeout
      --log-file string              Log everything to this file
      --log-level string             Log level
      --low-level-retries int        Number of low level retries
      --progress                     Show progress during transfer
      --retries int                  Retry operations this many times
      --sftp-concurrency int         The maximum number of outstanding requests
      --stats Duration               Interval between printing stats
      --stats-one-line               Make the stats fit on one line
      --timeout Duration             IO idle timeout
      --transfers int                Number of file transfers to run in parallel
""")
        return 0

    if befehl == "version":
        print("rclone v" + os.environ.get("ATTRAPPE_VERSION", "1.70.0"))
        print("- os/version: attrappe")
        return 0
    if befehl == "obscure":
        print("VERSCHLEIERT")
        return 0
    if befehl == "lsjson":
        print(os.environ.get("ATTRAPPE_LSJSON", "[]"))
        return 0
    if befehl in ("mkdir", "copy", "rcat", "deletefile", "lsd"):
        if befehl == "rcat":
            sys.stdin.read()
        return 0
    if befehl == "bisync":
        print("INFO : Bisync beginnt")
        print("INFO : Eine Datei übertragen")
        print("INFO : Bisync erfolgreich")
        return int(os.environ.get("ATTRAPPE_BISYNC_CODE", "0"))

    print(f"Attrappe kennt den Befehl nicht: {befehl}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
