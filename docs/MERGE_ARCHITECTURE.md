# LANMessengerPro + SoftRose Merge Architecture

Status: accepted implementation direction (2026-11-25)
Target branch: `main`
Decision: keep LANMessengerPro as the application and trusted transport foundation; port SoftRose's user-facing workflows and mature LAN-messenger features into it. Do not embed or expose the SoftRose plaintext network service.

## 1. Audited source baselines

### LANMessengerPro (current main)

The current repository is a Python 3.11+ / PySide6 desktop application. Its source tree contains:
- `network.py`: UDP multicast/broadcast presence discovery.
- `transport.py`: TLS 1.2+ message transport, per-installation ECDSA identity, SHA-256 certificate fingerprint pinning, explicit peer trust, message ACKs.
- `storage.py`: SQLite contacts, per-peer message history, transfer records, and durable outgoing-message states.
- `ui/main_window.py`, `ui/style.py`, dialogs, pairing and history views.
- `build.py`: Windows Nuitka standalone build entry point.

The latest inspected main commit is `3c5e22e230f60527788d6a7c1aeffc3cf520a9ae`. The latest two CI runs on main (commits `3c5e22e` and `1d73345`) completed successfully. This is CI evidence only; it is not a real multi-PC LAN acceptance test.

### SoftRose 1.0.0 (user-provided archive)

The archive contains a Python service, asyncio TCP protocol, UDP discovery, SQLite store, local HTTP API, browser UI, tray integration, scripts and prebuilt Windows binaries.

Useful workflows to port:
- Presence/status and profile editing.
- Search across contacts and conversations.
- Message editing, typing, delivered/read states, notifications and offline queue.
- Drag/drop files and whole folders, accept/reject, progress, sender/date folder layout, and configurable receive directory.
- Persian/English localization, RTL, light/dark themes, tray and startup controls.
- One-click deployment and uninstall behavior.

SoftRose's current LAN protocol in `softrose/net/core.py` uses ordinary TCP streams and does not wrap peer traffic in TLS. Discovery packets are self-asserted UDP JSON. Its localhost UI API token is a separate local-browser control and does not authenticate remote LAN peers. These components must not be reused as the trusted peer transport.

## 2. Architectural decisions

1. **Desktop shell:** PySide6 remains the sole desktop shell. Port SoftRose interaction patterns and visual hierarchy into Qt widgets; do not ship a second Edge/WebView application.
2. **Discovery:** retain LANMessengerPro's multicast/broadcast discovery, but treat every discovered record as untrusted metadata. Discovery never grants permission to send or receive.
3. **Peer identity:** retain TLS 1.2+ and explicit certificate fingerprint pairing. Every message and file-transfer operation must verify the paired peer identity before acting.
4. **Transport:** extend the pinned TLS transport with a versioned transfer protocol. Do not open a parallel plaintext SoftRose TCP listener.
5. **Files:** stream bounded chunks; compute SHA-256 while sending and receiving; write only to a temporary file under the selected receive root; validate relative paths; atomically rename only after size and digest verification. Reject path traversal, absolute paths, drive prefixes, alternate data stream syntax, symlinks/reparse-point escapes, duplicate transfer IDs, and over-limit transfers.
6. **Folders:** represent a folder as a manifest of relative file paths and sizes. Apply per-file and aggregate limits, reject unsafe entries before accepting, preserve safe relative structure, and keep the sender-specific/date-specific destination layout.
7. **Persistence:** SQLite remains authoritative for message history, transfer metadata, and durable queue state. File bytes are not stored in SQLite.
8. **Settings:** migrate SoftRose's profile, language, theme, notifications, receive-folder, startup and tray preferences into typed LANMessengerPro settings. Never import SoftRose's network trust claims or plaintext peer records as trusted devices.
9. **Packaging:** keep a reproducible Windows build from source. Produce a portable folder first, then a single-file installer/EXE after runtime and clean-machine tests. Do not bundle the user's existing SoftRose prebuilt EXEs.

## 3. Feature port matrix

| SoftRose capability | LANMessengerPro destination | Merge rule |
|---|---|---|
| Modern chat list and conversation layout | PySide6 main window | Rebuild natively; preserve Qt event/thread model |
| Persian/English + RTL | UI localization layer | Preserve translation keys and RTL behavior |
| Light/dark themes | `ui/style.py` and settings | Port palette and component states |
| Presence/status/profile | discovery + settings + contacts | Presence remains advisory/untrusted |
| Typing indicator | TLS protocol + UI signal | Only from a paired peer |
| Edit message | message schema + TLS protocol | Authorize edits against original sender/message |
| Delivered/read receipts | message state + TLS protocol | Persist before acknowledging |
| Offline queue | SQLite outbox | Preserve stable IDs, retry and deduplication |
| File transfer | TLS transport + transfer service | Reimplement; no SoftRose plaintext socket |
| Folder transfer | manifest-based TLS transfer | Validate every path and aggregate limits |
| Search/history | SQLite queries + history UI | Keep per-contact history |
| Notifications/tray | Qt system tray | Avoid SoftRose ctypes tray implementation |
| Autostart | Windows-specific settings helper | Per-user opt-in; reversible uninstall |
| Portable setup | build/deploy scripts | Build from LANMessengerPro source only |

## 4. Delivery stages

### Stage A — source audit and architecture baseline
- [x] Inspect current LANMessengerPro main tree and latest CI state.
- [x] Inspect SoftRose archive structure and network/API implementation.
- [x] Record security boundary and feature mapping.

### Stage B — secure file-transfer core
- [ ] Define versioned offer/accept/chunk/complete/cancel frames.
- [ ] Add bounded streaming and backpressure over the pinned TLS connection.
- [ ] Verify peer ID + pinned certificate for every transfer.
- [ ] Add SHA-256, size checks, atomic temporary-file handling and safe destination resolution.
- [ ] Add deterministic unit tests for corruption, truncation, duplicate IDs, unsafe paths, limits and cancellation.

### Stage C — transfer UI and folder workflows
- [ ] Add drag/drop and file/folder picker.
- [ ] Add accept/reject and per-transfer progress/cancel states.
- [ ] Add sender/date subfolders and configurable receive root.
- [ ] Persist transfer state and recover interrupted transfers safely.

### Stage D — SoftRose interaction parity
- [ ] Port profile/status, typing, read receipts, edit, search, localization and notification workflows.
- [ ] Add group/broadcast messaging only after per-recipient trust and delivery semantics are defined.
- [ ] Audit all UI actions for keyboard, accessibility and error feedback.

### Stage E — portable release
- [ ] Add first-run setup and safe settings migration.
- [ ] Verify tray/autostart/uninstall behavior on Windows 11.
- [ ] Build portable output and installer with pinned dependencies.
- [ ] Test on two clean Windows machines and a 10–30-device LAN where available.
- [ ] Publish checksums and a release checklist.

## 5. Security and acceptance gates

- No plaintext LAN fallback.
- Unknown or changed peer certificates are rejected until explicit re-pairing.
- UDP discovery data is never treated as identity proof.
- No file is made visible at its final destination before integrity verification.
- All remote filenames and relative paths are treated as hostile input.
- File-size, folder-count, aggregate-size, frame-size, concurrency and timeout limits are enforced.
- Transfer progress and state changes are emitted to the UI thread safely.
- A successful CI run is not represented as proof of multi-machine interoperability.
- Release is blocked until the two-device LAN test, interrupted-transfer test, and clean-machine packaging test pass.

## 6. Immediate next implementation target

Implement Stage B first, behind a transport-level API that does not depend on Qt. Then wire the tested API into the existing PySide6 window. This keeps the security-critical protocol independently testable and prevents UI work from bypassing peer verification or file validation.
