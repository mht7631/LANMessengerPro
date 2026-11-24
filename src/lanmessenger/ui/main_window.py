from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QListWidget,
    QListWidgetItem, QLineEdit, QPushButton, QTextEdit, QToolBar, QSplitter,
    QSystemTrayIcon, QMenu, QMessageBox, QFileDialog, QApplication, QDialog
)

from ..network import LanDiscovery
from .dialogs import SettingsDialog
from .history import HistoryViewer


class MainWindow(QMainWindow):
    peers_updated = Signal(object)

    def __init__(self, store, config, save_config, apply_theme):
        super().__init__()
        self.store, self.config = store, config
        self.save_config_cb, self.apply_theme = save_config, apply_theme
        self.current_peer = None
        self._contact_rows = []
        self.network = LanDiscovery(
            peer_id=config["peer_id"],
            display_name=config["display_name"],
            on_peers=self.peers_updated.emit,
        )
        self.peers_updated.connect(self._on_peers_updated)
        self.setWindowTitle("LAN Messenger Pro")
        self.resize(1050, 690)
        self._build_ui()
        self._build_tray()
        self.refresh_contacts()
        self.network.start()
        self.statusBar().showMessage("LAN discovery active • Waiting for peers on this network")

    def _build_ui(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for label, callback in [
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
        self.chat_subtitle = QLabel("Peer-to-peer discovery • Messaging transport is the next milestone")
        self.chat_subtitle.setObjectName("Muted")
        chat_layout.addWidget(self.chat_subtitle)
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        chat_layout.addWidget(self.transcript, 1)
        composer = QHBoxLayout()
        self.message = QLineEdit()
        self.message.setPlaceholderText("Messaging will activate in the next network milestone…")
        self.message.setEnabled(False)
        send_file = QPushButton("Attach")
        send_file.setEnabled(False)
        send = QPushButton("Send")
        send.setObjectName("Primary")
        send.setEnabled(False)
        composer.addWidget(send_file)
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
        count = len(peers)
        self.statusBar().showMessage(
            f"LAN discovery active • {count} peer(s) online"
        )

    def refresh_contacts(self):
        selected = self.current_peer
        self.people.clear()
        self._contact_rows = self.store.contacts()
        for contact in self._contact_rows:
            online = contact["status"] == "online"
            marker = "🟢" if online else "⚪"
            label = f"{marker}  {contact['display_name']}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, contact["peer_id"])
            item.setToolTip(
                f"{contact['display_name']} • {contact['status']}"
                + (f" • {contact['address']}" if contact["address"] else "")
            )
            self.people.addItem(item)
            if selected and contact["peer_id"] == selected:
                self.people.setCurrentItem(item)
        self.my_info.setText(f"My Info  •  {self.config['display_name']}")

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
            self.chat_subtitle.setText(f"Online • {contact['address']}")
        else:
            self.chat_subtitle.setText("Offline • Local history remains available")

    def _append_message(self, direction, body, timestamp=""):
        prefix = "You" if direction == "outgoing" else self.chat_title.text()
        safe_body = (body.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace("\n", "<br>"))
        self.transcript.append(
            f"<b>{prefix}</b> <span style='color:gray'>{timestamp}</span><br>{safe_body}<br>"
        )

    def filter_contacts(self, query):
        q = query.casefold()
        for i in range(self.people.count()):
            self.people.item(i).setHidden(q not in self.people.item(i).text().casefold())

    def contact_menu(self, point):
        item = self.people.itemAt(point)
        if not item:
            return
        menu = QMenu(self)
        open_chat = menu.addAction("Open chat")
        history = menu.addAction("View history")
        open_chat.triggered.connect(lambda: self.select_contact(item))
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
        QMessageBox.information(
            self, "Settings saved",
            "Your profile was saved. The new display name is now being advertised on the LAN."
        )

    def closeEvent(self, event):
        self.network.stop()
        if self.tray.isVisible():
            self.hide()
            self.tray.showMessage("LAN Messenger Pro", "The app is still running in the system tray.")
            event.ignore()
            self.network.start()
        else:
            event.accept()
