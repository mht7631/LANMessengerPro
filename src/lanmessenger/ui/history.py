from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QTableWidget,
    QTableWidgetItem, QLabel, QLineEdit, QPushButton, QWidget, QTabWidget,
)
from PySide6.QtCore import Qt


class HistoryViewer(QDialog):
    def __init__(self, store, contacts, parent=None):
        super().__init__(parent)
        self.store = store
        self.contacts = contacts
        self.setWindowTitle("History Viewer")
        self.resize(980, 600)
        layout = QHBoxLayout(self)
        self.people = QListWidget()
        self.people.setMaximumWidth(210)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Date / Time", "Direction", "Type", "Message"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.transfer_table = QTableWidget(0, 5)
        self.transfer_table.setHorizontalHeaderLabels(["Date / Time", "Direction", "File / Folder", "Size", "Status"])
        self.transfer_table.horizontalHeader().setStretchLastSection(True)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.table, "Messages")
        self.tabs.addTab(self.transfer_table, "File transfers")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search history…")
        right = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("Conversation history"))
        top.addStretch()
        top.addWidget(self.search)
        right.addLayout(top)
        right.addWidget(self.tabs)
        layout.addWidget(self.people)
        panel = QWidget()
        panel.setLayout(right)
        layout.addWidget(panel, 1)

        for contact in contacts:
            self.people.addItem(contact["display_name"])
        self._peer_ids = [contact["peer_id"] for contact in contacts]
        self.people.currentRowChanged.connect(self.load_history)
        self.search.textChanged.connect(self.filter_rows)
        if self._peer_ids:
            self.people.setCurrentRow(0)

    def load_history(self, row):
        self.table.setRowCount(0)
        self.transfer_table.setRowCount(0)
        if row < 0 or row >= len(self._peer_ids):
            return

        peer_id = self._peer_ids[row]
        for message in self.store.messages(peer_id):
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [
                message["created_at"], message["direction"].title(),
                message["kind"].title(), message["body"],
            ]
            for col, value in enumerate(values):
                self.table.setItem(r, col, QTableWidgetItem(str(value)))

        for transfer in self.store.transfers(peer_id):
            r = self.transfer_table.rowCount()
            self.transfer_table.insertRow(r)
            size = int(transfer["size_bytes"])
            size_text = f"{size / (1024 * 1024):.2f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"
            values = [
                transfer["created_at"], transfer["direction"].title(),
                transfer["filename"], size_text, transfer["status"].title(),
            ]
            for col, value in enumerate(values):
                self.transfer_table.setItem(r, col, QTableWidgetItem(str(value)))
        self.filter_rows(self.search.text())

    def filter_rows(self, query):
        q = query.casefold()
        for table in (self.table, self.transfer_table):
            for row in range(table.rowCount()):
                visible = any(
                    q in (table.item(row, col).text().casefold() if table.item(row, col) else "")
                    for col in range(table.columnCount())
                )
                table.setRowHidden(row, not visible)
