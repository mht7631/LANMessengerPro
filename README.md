# LAN Messenger Pro

Windows LAN messenger built with Python and PySide6. Current milestone: UDP-based peer discovery and presence.

See [README_FA.md](README_FA.md) for setup instructions and the detailed implementation status in Persian.

## Current milestone
- Persistent device identity
- LAN peer discovery via UDP multicast/broadcast
- Online/offline presence and display-name announcements
- SQLite-backed local contacts and per-peer history
- Modern PySide6 UI, tray, light/dark themes

Chat transport, secure pairing, and file transfer are not implemented yet. Discovery packets are unauthenticated and unencrypted; use only on a trusted private LAN.

## Run
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m lanmessenger
```

Run on two or more Windows PCs on the same LAN. Permit the application on Private networks if Windows Firewall asks.