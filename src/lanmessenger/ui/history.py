from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QTableWidget, QTableWidgetItem, QLabel, QLineEdit, QPushButton, QWidget
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
        self.table.setHorizontalHeaderLabels(["Date / Time", "Direction", "Type", "Message / File"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search history…")
        right = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("Conversation history"))
        top.addStretch()
        top.addWidget(self.search)
        right.addLayout(top)
        right.addWidget(self.table)
        layout.addWidget(self.people)
        panel = QWidget()
        panel.setLayout(right)
        layout.addWidget(panel, 1)
        for c in contacts:
            self.people.addItem(c["display_name"])
        self._peer_ids = [c["peer_id"] for c in contacts]
        self.people.currentRowChanged.connect(self.load_history)
        self.search.textChanged.connect(self.filter_rows)
        if self._peer_ids:
            self.people.setCurrentRow(0)

    def load_history(self, row):
        self.table.setRowCount(0)
        if row < 0 or row >= len(self._peer_ids):
            return
        for msg in self.store.messages(self._peer_ids[row]):
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [msg["created_at"], msg["direction"].title(), msg["kind"].title(), msg["body"]]
            for col, value in enumerate(values):
                self.table.setItem(r, col, QTableWidgetItem(str(value)))
        self.filter_rows(self.search.text())

    def filter_rows(self, query):
        q = query.casefold()
        for r in range(self.table.rowCount()):
            visible = any(q in (self.table.item(r, c).text().casefold() if self.table.item(r,c) else "") for c in range(4))
            self.table.setRowHidden(r, not visible)
