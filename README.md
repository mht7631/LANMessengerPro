# LAN Messenger Pro

A Windows desktop LAN messenger built with Python and PySide6. The current development milestone includes authenticated TLS chat and user-approved file/folder transfers.

See [README_FA.md](README_FA.md) for Persian setup instructions and the detailed status.

## Implemented

- Persistent per-installation ECDSA device identity
- UDP multicast/broadcast discovery and online presence
- Manual two-way pairing using independently verified SHA-256 certificate fingerprints
- TLS 1.2+ transport; unpaired peers are rejected
- Per-contact SQLite message history and acknowledged message delivery
- Queued outgoing messages with retry after peers return online
- Single-file transfer with explicit receiver approval
- Folder transfer preserving relative paths, with one approval per folder
- SHA-256 and declared-size verification before files are published
- Sender-specific receive directories, collision-safe file creation, and transfer history
- Light/dark themes, system tray, settings, and configurable receive directory

## Transfer limits and current limitations

- Maximum single file: 512 MiB
- Maximum folder: 1,024 files and 2 GiB aggregate
- Folder contents are sent sequentially; interrupted transfers do not resume automatically
- Group chat, typing indicators, read receipts, message editing, and code signing are not implemented yet
- UDP discovery announcements are not authenticated; they are hints only. Chat and file payloads use the paired TLS channel.
- Pairing is manual and must be completed on both devices using a separate trusted channel. Do not expose the listener to the public internet.

## Run from source

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m lanmessenger
```

Run on two or more PCs on the same private LAN. Allow the application through Windows Firewall only on Private networks when prompted.

## Build

```powershell
python -m pip install -r requirements.txt
python -m pip install nuitka
python build.py
```
