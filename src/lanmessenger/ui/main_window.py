from pathlib import Path
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QListWidget,
    QListWidgetItem, QLineEdit, QPushButton, QTextEdit, QToolBar, QSplitter,
    QSystemTrayIcon, QMenu, QMessageBox, QApplication, QDialog, QFileDialog
)

from ..config import APP_DIR
from ..network import LanDiscovery
from ..transport import PinnedTlsTransport, PairingRequired
from .dialogs import SettingsDialog
from .history import HistoryViewer
from .pairing import PairingDialog


class MainWindow(QMainWindow):
    peers_updated = Signal(object)
    incoming_message = Signal(object)
    send_finished = Signal(object)
    file_offer_requested = Signal(object)
    file_received = Signal(object)

    def __init__(self, store, config, save_config, apply_theme):
        super().__init__()
        self.store, self.config = store, config
        self.save_config_cb, self.apply_theme = save_config, apply_theme
        self.current_peer = None
        self._inflight_messages = set()
        self._contact_rows = []
        trusted = config.setdefault("trusted_peers", {})
        self.transport = PinnedTlsTransport(
            config["peer_id"], APP_DIR / "identity", {},
            on_message=self._persist_incoming_message,
            on_error=lambda message: self.send_finished.emit(("error", message)),
            on_file_offer=self._request_file_destination,
            on_file_received=self._file_received_worker,
        )
        self.transport.start()
        for peer_id, data in trusted.items():
            try:
                self.transport.trust_peer(peer_id, data["fingerprint"], data["certificate"])
            except (KeyError, TypeError, ValueError):
                continue
        self.network = LanDiscovery(
            peer_id=config["peer_id"],
            display_name=config["display_name"],
            on_peers=self.peers_updated.emit,
            tcp_port=self.transport.port,
        )
        self.peers_updated.connect(self._on_peers_updated)
        self.incoming_message.connect(self._on_incoming_message)
        self.send_finished.connect(self._on_send_finished)
        self.file_offer_requested.connect(self._show_file_offer)
        self.file_received.connect(self._on_file_received)
        self.setWindowTitle("LAN Messenger Pro")
        self.resize(1050, 690)
        self._build_ui()
        self._build_tray()
        self.refresh_contacts()
        self.network.start()
        self.statusBar().showMessage("LAN discovery and TLS listener active")

    def _build_ui(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for label, callback in [
            ("Pair device", self.open_pairing),
            ("My Info", self.open_settings),
            ("History", self.open_history),
            ("Settings", self.open_settings),
        ]:
            action = QAction(label, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter()
        outer.addWidget(splitter)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(225)
        sidebar.setMaximumWidth(290)
        side = QVBoxLayout(sidebar)
        brand = QLabel("  ●  LAN Messenger Pro")
        brand.setStyleSheet("font-size: 14pt; font-weight: 700; padding: 13px 8px;")
        side.addWidget(brand)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search people…")
        side.addWidget(self.search)
        self.people = QListWidget()
        self.people.itemClicked.connect(self.select_contact)
        self.people.setContextMenuPolicy(Qt.CustomContextMenu)
        self.people.customContextMenuRequested.connect(self.contact_menu)
        side.addWidget(self.people, 1)
        self.my_info = QLabel()
        self.my_info.setObjectName("Muted")
        side.addWidget(self.my_info)
        splitter.addWidget(sidebar)

        chat = QWidget()
        chat_layout = QVBoxLayout(chat)
        chat_layout.setContentsMargins(18, 14, 18, 14)
        self.chat_title = QLabel("Select a contact")
        self.chat_title.setStyleSheet("font-size: 15pt; font-weight: 650;")
        chat_layout.addWidget(self.chat_title)
        self.chat_subtitle = QLabel("TLS encrypted transport • Pair devices to start chatting")
        self.chat_subtitle.setObjectName("Muted")
        chat_layout.addWidget(self.chat_subtitle)
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        chat_layout.addWidget(self.transcript, 1)
        composer = QHBoxLayout()
        self.message = QLineEdit()
        self.message.setPlaceholderText("Write a message…")
        self.message.returnPressed.connect(self.send_current_message)
        attach = QPushButton("Attach file…")
        attach.clicked.connect(self.send_file_dialog)
        send = QPushButton("Send")
        send.setObjectName("Primary")
        send.clicked.connect(self.send_current_message)
        composer.addWidget(attach)
        composer.addWidget(self.message, 1)
        composer.addWidget(send)
        chat_layout.addLayout(composer)
        splitter.addWidget(chat)
        splitter.setSizes([250, 800])
        self.search.textChanged.connect(self.filter_contacts)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("LAN Messenger Pro")
        menu = QMenu()
        show = menu.addAction("Open")
        show.triggered.connect(self.showNormal)
        quit_action = menu.addAction("Exit")
        quit_action.triggered.connect(QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.showNormal()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()

    def _on_peers_updated(self, peers):
        self.store.sync_discovered_peers(peers)
        self.refresh_contacts()
        self.statusBar().showMessage(f"LAN discovery active • {len(peers)} peer(s) online")
        self._dispatch_pending()

    def refresh_contacts(self):
        selected = self.current_peer
        self.people.clear()
        self._contact_rows = self.store.contacts()
        for contact in self._contact_rows:
            online = contact["status"] == "online"
            paired = contact["peer_id"] in self.transport.trusted
            marker = "🔐" if paired and online else ("🟢" if online else "⚪")
            item = QListWidgetItem(f"{marker}  {contact['display_name']}")
            item.setData(Qt.ItemDataRole.UserRole, contact["peer_id"])
            item.setToolTip(f"{contact['display_name']} • {contact['status']} • {'Paired' if paired else 'Not paired'}")
            self.people.addItem(item)
            if selected and contact["peer_id"] == selected:
                self.people.setCurrentItem(item)
        self.my_info.setText(f"My Info • {self.config['display_name']}")

    def filter_contacts(self, query):
        q = query.casefold()
        for i in range(self.people.count()):
            self.people.item(i).setHidden(q not in self.people.item(i).text().casefold())

    def select_contact(self, item):
        self.current_peer = item.data(Qt.ItemDataRole.UserRole)
        contact = next((c for c in self._contact_rows if c["peer_id"] == self.current_peer), None)
        self.chat_title.setText(contact["display_name"] if contact else item.text().split("  ", 1)[-1])
        self.transcript.clear()
        for msg in self.store.messages(self.current_peer):
            self._append_message(msg["direction"], msg["body"], msg["created_at"])
        if contact and contact["status"] == "online":
            self.chat_subtitle.setText(f"{'Paired' if self.current_peer in self.transport.trusted else 'Not paired'} • {contact['address']}:{contact['tcp_port']}")
        else:
            self.chat_subtitle.setText("Offline • Local history remains available")

    def _append_message(self, direction, body, timestamp=""):
        prefix = "You" if direction == "outgoing" else self.chat_title.text()
        safe_body = (body.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace("\n", "<br>"))
        self.transcript.append(f"<b>{prefix}</b> <span style='color:gray'>{timestamp}</span><br>{safe_body}<br>")

    def send_current_message(self):
        if not self.current_peer:
            QMessageBox.information(self, 'Select a contact', 'Select a contact first.')
            return
        body = self.message.text().strip()
        if not body:
            return
        peer_id = self.current_peer
        self.store.add_message(peer_id, 'outgoing', body, delivery_status='queued')
        self._append_message('outgoing', body)
        self.message.clear()
        self._dispatch_pending(peer_id)

    def _dispatch_pending(self, only_peer=None):
        contacts = {c['peer_id']: c for c in self._contact_rows}
        for msg in self.store.pending_messages(only_peer):
            message_id = msg['message_id']
            peer_id = msg['peer_id']
            contact = contacts.get(peer_id)
            if (message_id in self._inflight_messages or not contact
                    or contact['status'] != 'online'
                    or peer_id not in self.transport.trusted):
                continue
            host, port = contact['address'], int(contact['tcp_port'] or 0)
            if not host or not port:
                continue
            self._inflight_messages.add(message_id)
            self.store.set_delivery_status(message_id, 'sending')
            threading.Thread(target=self._send_worker,
                args=(host, port, peer_id, msg['body'], message_id),
                daemon=True, name='LAN-message-send').start()

    def _send_worker(self, host, port, peer_id, body, message_id):
        try:
            self.transport.send_message(host, port, peer_id, body, message_id=message_id)
            self.send_finished.emit(('sent', peer_id, message_id))
        except Exception as exc:
            self.send_finished.emit(('error', peer_id, message_id, str(exc)))

    def send_file_dialog(self):
        if not self.current_peer:
            QMessageBox.information(self, "Select a contact", "Select a contact first.")
            return
        contact = next((c for c in self._contact_rows if c["peer_id"] == self.current_peer), None)
        if not contact or contact["status"] != "online":
            QMessageBox.information(self, "Peer offline", "File transfer requires the recipient to be online.")
            return
        if self.current_peer not in self.transport.trusted:
            QMessageBox.information(self, "Pairing required", "Pair this device before sending files.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Send a file")
        if not filename:
            return
        path = Path(filename)
        self.statusBar().showMessage(f"Sending {path.name}…")
        threading.Thread(
            target=self._send_file_worker,
            args=(contact["address"], int(contact["tcp_port"] or 0), self.current_peer, path),
            daemon=True,
            name="LAN-file-send",
        ).start()

    def _send_file_worker(self, host, port, peer_id, path):
        try:
            transfer_id = self.transport.send_file(host, port, peer_id, path)
            self.send_finished.emit(("file_sent", peer_id, transfer_id, path.name, path.stat().st_size))
        except Exception as exc:
            self.send_finished.emit(("file_error", peer_id, str(exc)))

    def _request_file_destination(self, packet):
        event = threading.Event()
        response = {}
        self.file_offer_requested.emit({"packet": packet, "event": event, "response": response})
        if not event.wait(90):
            return None
        return response.get("root")

    def _show_file_offer(self, request):
        packet = request["packet"]
        contact = next((c for c in self._contact_rows if c["peer_id"] == packet["sender_id"]), None)
        sender = contact["display_name"] if contact else packet["sender_id"]
        size_mb = packet["size"] / (1024 * 1024)
        answer = QMessageBox.question(
            self,
            "Incoming file",
            f"{sender} wants to send {packet['filename']} ({size_mb:.2f} MB).\n\nAccept this file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            root = Path(self.config["receive_dir"]) / packet["sender_id"]
            root.mkdir(parents=True, exist_ok=True)
            request["response"]["root"] = root
        request["event"].set()

    def _file_received_worker(self, packet, saved_path):
        self.store.add_transfer(
            packet["transfer_id"], packet["sender_id"], packet["filename"],
            packet["size"], "incoming", "completed",
        )
        self.file_received.emit({"packet": packet, "path": saved_path})

    def _on_file_received(self, result):
        packet, path = result["packet"], result["path"]
        self.tray.showMessage("LAN Messenger Pro", f"Received {path.name}")
        self.statusBar().showMessage(f"File received and verified: {path}", 12000)

    def _persist_incoming_message(self, packet):
        """Persist on the transport worker before it sends the protocol ACK."""
        message_id = packet["message_id"]
        if not self.store.has_message(message_id):
            self.store.add_message(
                packet["sender_id"], "incoming", packet["body"],
                message_id=message_id,
            )
        self.incoming_message.emit(packet)

    def _on_incoming_message(self, packet):
        peer_id = packet["sender_id"]
        if self.current_peer == peer_id:
            self.transcript.clear()
            for msg in self.store.messages(peer_id):
                self._append_message(msg["direction"], msg["body"], msg["created_at"])
        self.tray.showMessage("LAN Messenger Pro", "New message received")
        self.statusBar().showMessage("New message received")

    def _on_send_finished(self, result):
        kind = result[0]
        if kind == "file_sent":
            _kind, peer_id, transfer_id, filename, size = result
            self.store.add_transfer(transfer_id, peer_id, filename, size, "outgoing", "completed")
            self.statusBar().showMessage(f"File sent and verified by recipient: {filename}", 12000)
            return
        if kind == "file_error":
            self.statusBar().showMessage(f"File transfer failed: {result[2]}", 12000)
            return
        if len(result) == 2:
            self.statusBar().showMessage(f'Transport error: {result[1]}', 10000)
            return
        if kind == 'sent':
            _kind, peer_id, message_id = result
            self._inflight_messages.discard(message_id)
            self.store.set_delivery_status(message_id, 'delivered')
            self.statusBar().showMessage('Message delivered and acknowledged by peer')
        else:
            _kind, peer_id, message_id, detail = result
            self._inflight_messages.discard(message_id)
            self.store.set_delivery_status(message_id, 'failed')
            self.statusBar().showMessage(f'Queued for retry: {detail}', 10000)

    def open_pairing(self):
        dialog = PairingDialog(self.config["peer_id"], self.transport.fingerprint, self.transport.certificate_pem, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        peer_id = values["peer_id"]
        if not peer_id or not values["host"]:
            QMessageBox.warning(self, "Pairing", "Device ID and IP address are required.")
            return
        try:
            self.transport.trust_peer(peer_id, values["fingerprint"], values["certificate"])
        except ValueError as exc:
            QMessageBox.warning(self, "Pairing failed", str(exc))
            return
        self.config.setdefault("trusted_peers", {})[peer_id] = {
            "fingerprint": values["fingerprint"].replace(":", "").lower(),
            "certificate": values["certificate"],
            "host": values["host"],
            "port": values["port"],
        }
        self.save_config_cb(self.config)
        self.refresh_contacts()
        QMessageBox.information(self, "Device paired", "The certificate fingerprint was verified and this device is now trusted. The other user must also pair your device.")

    def contact_menu(self, point):
        item = self.people.itemAt(point)
        if not item:
            return
        menu = QMenu(self)
        open_chat = menu.addAction("Open chat")
        pair = menu.addAction("Pair device…")
        history = menu.addAction("View history")
        open_chat.triggered.connect(lambda: self.select_contact(item))
        pair.triggered.connect(self.open_pairing)
        history.triggered.connect(self.open_history)
        menu.exec(self.people.mapToGlobal(point))

    def open_history(self):
        HistoryViewer(self.store, self._contact_rows, self).exec()

    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if values is None:
            return
        self.config.update(values)
        Path(self.config["receive_dir"]).mkdir(parents=True, exist_ok=True)
        self.save_config_cb(self.config)
        self.apply_theme(self.config["theme"])
        self.network.update_profile(self.config["display_name"])
        self.refresh_contacts()
        QMessageBox.information(self, "Settings saved", "Your profile was saved and is being advertised on the LAN.")

    def closeEvent(self, event):
        if self.tray.isVisible():
            self.hide()
            self.tray.showMessage("LAN Messenger Pro", "The app is still running in the system tray.")
            event.ignore()
        else:
            event.accept()

    def shutdown(self):
        self.network.stop()
        self.transport.stop()
