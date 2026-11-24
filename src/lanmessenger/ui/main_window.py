from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QListWidget,
    QListWidgetItem, QLineEdit, QPushButton, QTextEdit, QToolBar, QStatusBar,
    QSplitter, QSystemTrayIcon, QMenu, QMessageBox, QFileDialog, QApplication,
    QDialog
)
from .dialogs import SettingsDialog
from .history import HistoryViewer

class MainWindow(QMainWindow):
    def __init__(self, store, config, save_config, apply_theme):
        super().__init__()
        self.store, self.config = store, config
        self.save_config_cb, self.apply_theme = save_config, apply_theme
        self.current_peer = None
        self.setWindowTitle("LAN Messenger Pro")
        self.resize(1050, 690)
        self._build_ui()
        self._build_tray()
        self.refresh_contacts()

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
        self.chat_subtitle = QLabel("Local prototype • LAN networking is not connected yet")
        self.chat_subtitle.setObjectName("Muted")
        chat_layout.addWidget(self.chat_subtitle)
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        chat_layout.addWidget(self.transcript, 1)
        composer = QHBoxLayout()
        self.message = QLineEdit()
        self.message.setPlaceholderText("Write a message…")
        self.message.returnPressed.connect(self.send_message)
        send_file = QPushButton("Attach")
        send_file.clicked.connect(self.choose_file)
        send = QPushButton("Send")
        send.setObjectName("Primary")
        send.clicked.connect(self.send_message)
        composer.addWidget(send_file)
        composer.addWidget(self.message, 1)
        composer.addWidget(send)
        chat_layout.addLayout(composer)
        splitter.addWidget(chat)
        splitter.setSizes([250, 800])
        self.statusBar().showMessage("Offline prototype • No network connections")
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
        self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def refresh_contacts(self):
        self.people.clear()
        self._contact_rows = self.store.contacts()
        for c in self._contact_rows:
            icon = "🟢" if c["status"] == "online" else ("🟡" if c["status"] == "away" else "⚪")
            item = QListWidgetItem(f"{icon}  {c['display_name']}")
            item.setData(Qt.ItemDataRole.UserRole, c["peer_id"])
            item.setToolTip(f"{c['display_name']} • {c['status']}")
            self.people.addItem(item)
        self.my_info.setText(f"My Info  •  {self.config['display_name']}")

    def filter_contacts(self, query):
        q = query.casefold()
        for i in range(self.people.count()):
            self.people.item(i).setHidden(q not in self.people.item(i).text().casefold())

    def select_contact(self, item):
        self.current_peer = item.data(Qt.ItemDataRole.UserRole)
        name = item.text().split("  ", 1)[-1]
        self.chat_title.setText(name)
        self.transcript.clear()
        for m in self.store.messages(self.current_peer):
            self._append_message(m["direction"], m["body"], m["created_at"])
        self.chat_subtitle.setText("Contact selected • Demo data; network transport pending")

    def _append_message(self, direction, body, timestamp=""):
        prefix = "You" if direction == "outgoing" else self.chat_title.text()
        self.transcript.append(f"<b>{prefix}</b> <span style='color:gray'>{timestamp}</span><br>{body}<br>")

    def send_message(self):
        body = self.message.text().strip()
        if not body or not self.current_peer:
            return
        self.store.add_message(self.current_peer, "outgoing", body)
        self._append_message("outgoing", body)
        self.message.clear()

    def choose_file(self):
        if not self.current_peer:
            QMessageBox.information(self, "Choose a contact", "Select a contact first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select a file")
        if path:
            QMessageBox.information(self, "Prototype", f"Selected file:\n{path}\n\nReal network transfer will be implemented in a later milestone.")

    def contact_menu(self, point):
        item = self.people.itemAt(point)
        if not item:
            return
        menu = QMenu(self)
        chat = menu.addAction("Open chat")
        history = menu.addAction("View history")
        chat.triggered.connect(lambda: self.select_contact(item))
        history.triggered.connect(self.open_history)
        menu.exec(self.people.mapToGlobal(point))

    def open_history(self):
        dlg = HistoryViewer(self.store, self._contact_rows, self)
        dlg.exec()

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            values = dlg.values()
            if values is None:
                return
            self.config.update(values)
            Path(self.config["receive_dir"]).mkdir(parents=True, exist_ok=True)
            self.save_config_cb(self.config)
            self.apply_theme(self.config["theme"])
            self.refresh_contacts()
            QMessageBox.information(
                self, "Settings saved",
                "Your local profile settings were saved.\n"
                "Network-wide display-name publishing will be enabled with the P2P identity service."
            )

    def closeEvent(self, event):
        if self.tray.isVisible():
            self.hide()
            self.tray.showMessage("LAN Messenger Pro", "The app is still running in the system tray.")
            event.ignore()
        else:
            event.accept()
