[Changelog](CHANGELOG.md) | [Releases](https://github.com/Stephan-Lefty/storage-box-sync/releases) | [TODO](TODO.md) | [🇩🇪 Deutsch](README.md)

<p align="center">
  <img src="assets/icon-256.png" alt="storage-box-sync" width="140">
</p>

# storage-box-sync

Keeps a local folder and a **Hetzner Storage Box** in sync in both directions –
and with it multiple computers with each other.
Runs on Linux, Windows and macOS. The interface and messages are in German
(English translation of messages is on the todo list).

```
PC Manjaro  ⇄  Storage Box  ⇄  PC Windows
                    ⇅
                 Notebook
```

Under the hood it uses [rclone bisync](https://rclone.org/bisync/) over SFTP.
`storage-box-sync` handles the tedious parts: setup, protection against data
loss, locking between multiple computers, scheduling on three operating systems,
and a GUI that doesn't require the command line.

## Features

* **Two-way sync.** Any computer may create, modify, rename and delete files.
  The Storage Box is the hub.
* **Conflicts are handled, not hidden.** If the same file was changed on two
  computers, the newer version wins by default; the losing version is kept as
  `letter.conflict-manjaro-pc.odt`. Nothing disappears silently.
* **Protection against the worst case.** If a drive is not mounted, the folder
  appears empty – a naive mirror would then wipe the Storage Box.
  Three safeguards prevent this: a sentinel file on both sides, a percentage-
  based deletion limit, and a dry-run mode that changes nothing.
* **Multiple computers without conflicts.** Before each run, the computer places
  a lock file on the Storage Box. If it finds a fresh lock from another machine,
  it waits until the next scheduled run.
* **Automatic.** On startup and every hour – via systemd (Linux), Task Scheduler
  (Windows) or launchd (macOS).
* **Considerate of the Storage Box.** Hetzner allows **ten simultaneous
  connections** across all protocols. The default of four transfers leaves room
  for backups and other accesses.

## Requirements

* Python 3.9 or newer
* **rclone 1.66 or newer** (`--conflict-resolve` is only available from 1.66;
  with 1.67+ the initial sync is smarter too)
* a Hetzner Storage Box with SSH access enabled
* for the GUI: PyQt6 (optional)

## Installation

### Linux and macOS

```bash
# rclone first
pamac install rclone            # Manjaro, Arch
sudo apt install rclone         # Debian, Ubuntu
brew install rclone             # macOS

# then the tool, cleanest with pipx
pipx install "git+https://github.com/Stephan-Lefty/storage-box-sync.git[fenster]"

# or without pipx
pip install --user "git+https://github.com/Stephan-Lefty/storage-box-sync.git[fenster]"
```

On Arch and Manjaro, PyQt6 is better installed via the package manager than pip:

```bash
pamac install python-pyqt6
pipx install --system-site-packages git+https://github.com/Stephan-Lefty/storage-box-sync.git
```

A `PKGBUILD` for a custom Arch package is in the `packaging/` folder.

### Windows

```powershell
winget install Rclone.Rclone
winget install Python.Python.3.12

pip install "git+https://github.com/Stephan-Lefty/storage-box-sync.git[fenster]"
```

After that, `storage-box-sync` (CLI), `storage-box-sync-fenster` and
`storage-box-sync-symbol` (without console window) are available.

### From the cloned source

```bash
git clone https://github.com/Stephan-Lefty/storage-box-sync.git
cd storage-box-sync
pip install -e ".[fenster,entwicklung]"
pytest
```

## Setup

With the GUI window:

```bash
storage-box-sync fenster
```

Or via the command-line wizard:

```bash
storage-box-sync einrichten
```

You will be asked for:

| Field | Example | Note |
|---|---|---|
| Local folder | `/mnt/raid/My-Storage-Box` | must exist |
| Server | `u123456.your-storagebox.de` | from the Hetzner console |
| User | `u123456` or `u123456-sub1` | sub-accounts work too |
| Port | `23` | faster SSH service; `22` is always open |
| Folder on the Box | `/` or `/data` | created if missing |

Then run the **initial sync** once. It compares both sides fully and brings
them into agreement – for files that exist on both sides, the newer version
wins. Nothing is deleted.

```bash
storage-box-sync grundlauf --probelauf    # dry run first
storage-box-sync grundlauf                # then for real
```

From now on, just run:

```bash
storage-box-sync abgleich
```

## Second and third computer

On every additional computer, do the same – with two things that matter:

1. **The same folder on the Storage Box.** Otherwise the computers sync
   different data sets.
2. **A unique computer name.** It goes into the lock files and conflict file
   names, so make it descriptive: `manjaro-pc`, `windows-office`, `notebook`.

```bash
storage-box-sync einrichten --rechnername windows-office
storage-box-sync grundlauf
```

The initial sync on the second computer fetches everything from the Storage Box
and uploads everything that only exists locally.

## Scheduling

```bash
storage-box-sync zeitplan ein       # on startup and every hour
storage-box-sync zeitplan status
storage-box-sync zeitplan aus
```

What gets created:

* **Linux:** `~/.config/systemd/user/storage-box-sync.{service,timer}` with
  `OnBootSec=3min`, `OnUnitActiveSec=1h`, `Persistent=true` and
  `RequiresMountsFor=<folder>`. To sync without an active session:
  `sudo loginctl enable-linger $USER`.
* **Windows:** two tasks in Task Scheduler – one at login (3 minutes delay),
  one every hour.
* **macOS:** a LaunchAgent with `RunAtLoad` and `StartInterval 3600`.

Multiple computers don't interfere: schedules are slightly offset, and the
lock file on the Storage Box catches the rest.

## System tray icon

```bash
storage-box-sync symbol
```

| Colour | Meaning |
|---|---|
| green | last sync successful |
| blue | sync in progress |
| yellow | no sync in over 26 hours |
| red | last run failed or drive not mounted |

Left-click opens the folder. Right-click gives access to sync, settings,
details and the log.

Auto-start:

* **Linux (KDE, GNOME, XFCE):** copy `packaging/storage-box-sync-symbol.desktop`
  to `~/.config/autostart/`.
* **Windows:** place a shortcut to `storage-box-sync-symbol.exe` in
  `shell:startup`.

## All commands

| Command | Purpose |
|---|---|
| `einrichten` | configure access, folder and schedule |
| `pruefen` | check connection, folder, sentinel file and locks |
| `grundlauf` | first full sync |
| `abgleich` | transfer changes in both directions |
| `status` | brief status (good, outdated, error …) |
| `protokoll` | show last log, `--liste` for all |
| `zeitplan ein\|aus\|status` | control automatic sync |
| `sperren` | view locks on the Storage Box, `--loesen` to clear |
| `ordner` | open local folder in file manager |
| `fenster` / `symbol` | start GUI |
| `info` | paths, versions, schedule command |

`--probelauf` shows what would happen for `grundlauf` and `abgleich` without
making any changes. `--still` writes only to the log – used by the scheduler.

## File locations

| | Linux | Windows |
|---|---|---|
| Settings | `~/.config/storage-box-sync/einstellungen.json` | `%APPDATA%\storage-box-sync\` |
| Exclusions | `…/ausnahmen.txt` | same |
| rclone config | `…/rclone.conf` | same |
| File lists | `~/.local/state/storage-box-sync/bisync/` | `%LOCALAPPDATA%\storage-box-sync\bisync\` |
| Logs | `~/.local/state/storage-box-sync/protokolle/` | `%LOCALAPPDATA%\storage-box-sync\protokolle\` |

The separate `rclone.conf` is intentional: any existing rclone configuration
of the user is left untouched.

## Security and limitations – honestly

* **The password is obfuscated, not encrypted.** `rclone obscure` is
  reversible. On Linux the file is stored with `600` permissions in your home
  directory, on Windows in the user profile. For stronger security, create an
  SSH key and enter it as the key file – then no password is stored.
* **The remote lock is good, but not watertight.** SFTP has no atomic
  "create only if not present". Two computers starting at the exact same second
  could both write a lock; a second look and a fixed tie-breaking rule mitigate
  this. The race cannot be ruled out completely. In practice, staggered
  schedules help.
* **Two-way sync is not a backup.** Deleting on one computer deletes
  everywhere. The Storage Box can create snapshots – that is the safety net
  below, though snapshots count towards used storage.
* **Changing exclusions requires a new initial sync.** After editing
  `ausnahmen.txt`, rclone requires a new `grundlauf`.

## Troubleshooting

**"The sentinel file RCLONE_TEST is missing"** – that is what it is there for.
The drive is not mounted, or the file was deleted. Mount it, then run
`storage-box-sync pruefen`.

**"Another computer is currently syncing"** – normal, the run is skipped and
retried next time. If a lock is stuck, use `storage-box-sync sperren` and
`--loesen`.

**rclone aborts with "must run --resync"** – the file lists no longer match,
e.g. after an interrupted run or a change to the exclusions.
`storage-box-sync grundlauf` resets everything.

**Connection errors or timeouts** – the ten connections of the Storage Box are
probably exhausted. Check other accesses (Nextcloud mount, backups, open SFTP
sessions) and lower the transfer count.

**Conflict files piling up** – two computers are editing the same files.
Either sync more frequently or separate the work more clearly.

## Contributing

```bash
pip install -e ".[fenster,entwicklung]"
pytest
```

The tests need neither rclone nor a Storage Box: `tests/attrappen/` contains
a mock that simulates rclone and records all calls.

## Licence

MIT – see [LICENSE](LICENSE).
