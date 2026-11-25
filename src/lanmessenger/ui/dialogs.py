from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QCheckBox,
    QPushButton, QFileDialog, QHBoxLayout, QMessageBox
)

class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        self.config = config.copy()
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(config.get("display_name", ""))
        self.theme = QComboBox()
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        self.theme.setCurrentIndex(0 if config.get("theme") == "light" else 1)
        self.receive = QLineEdit(config.get("receive_dir", ""))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.pick_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.receive, 1)
        folder_row.addWidget(browse)
        self.start_min = QCheckBox("Start minimized")
        self.start_min.setChecked(bool(config.get("start_minimized", False)))
        form.addRow("My display name", self.name)
        form.addRow("Appearance", self.theme)
        form.addRow("Received files folder", folder_row)
        form.addRow("", self.start_min)
        root.addLayout(form)
        note = QCheckBox("Display-name changes are announced to peers on the LAN.")
        note.setChecked(True)
        note.setEnabled(False)
        root.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setObjectName("Primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose received-files folder", self.receive.text())
        if folder:
            self.receive.setText(folder)

    def values(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid name", "Display name cannot be empty.")
            return None
        return {
            "display_name": name,
            "theme": self.theme.currentData(),
            "receive_dir": str(Path(self.receive.text()).expanduser()),
            "start_minimized": self.start_min.isChecked(),
        }
