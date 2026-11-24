from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QSpinBox,
    QPushButton, QHBoxLayout, QApplication, QLabel
)


class PairingDialog(QDialog):
    """Manual out-of-band pairing: compare fingerprints before trusting a peer."""

    def __init__(self, own_fingerprint: str, own_certificate: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pair a trusted device")
        self.setMinimumSize(650, 620)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Share your device identity with the other person using a trusted channel."))
        self.own_fp = QLineEdit(own_fingerprint)
        self.own_fp.setReadOnly(True)
        self.own_cert = QTextEdit()
        self.own_cert.setPlainText(own_certificate)
        self.own_cert.setReadOnly(True)
        copy = QPushButton("Copy my fingerprint")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(own_fingerprint))
        copy_cert = QPushButton("Copy my certificate")
        copy_cert.clicked.connect(lambda: QApplication.clipboard().setText(own_certificate))
        root.addWidget(QLabel("My SHA-256 fingerprint"))
        root.addWidget(self.own_fp)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(copy_cert)
        root.addLayout(row)
        form = QFormLayout()
        self.peer_id = QLineEdit()
        self.peer_id.setPlaceholderText("Exact device ID from the other user")
        self.host = QLineEdit()
        self.host.setPlaceholderText("e.g. 192.168.1.25")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(47888)
        self.fingerprint = QLineEdit()
        self.fingerprint.setPlaceholderText("64 hexadecimal characters")
        form.addRow("Other device ID", self.peer_id)
        form.addRow("Other device IP", self.host)
        form.addRow("Message port", self.port)
        form.addRow("Other SHA-256 fingerprint", self.fingerprint)
        root.addLayout(form)
        root.addWidget(QLabel("Paste the other device's PEM certificate (verify its fingerprint independently):"))
        self.certificate = QTextEdit()
        self.certificate.setPlaceholderText("-----BEGIN CERTIFICATE-----")
        root.addWidget(self.certificate, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        save = QPushButton("Trust device")
        save.setObjectName("Primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def values(self):
        return {
            "peer_id": self.peer_id.text().strip(),
            "host": self.host.text().strip(),
            "port": self.port.value(),
            "fingerprint": self.fingerprint.text().strip(),
            "certificate": self.certificate.toPlainText().strip(),
        }
