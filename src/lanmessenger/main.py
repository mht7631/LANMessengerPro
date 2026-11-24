import sys
from PySide6.QtWidgets import QApplication
from .config import load_config, save_config, DEFAULT_RECEIVE_DIR
from .storage import Store
from .ui.main_window import MainWindow
from .ui import style

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LAN Messenger Pro")
    app.setOrganizationName("LANMessengerPro")
    config = load_config()
    store = Store()
    store.seed_demo()
    from pathlib import Path
    Path(config.get("receive_dir", DEFAULT_RECEIVE_DIR)).mkdir(parents=True, exist_ok=True)

    def apply_theme(theme):
        app.setStyleSheet(style.DARK if theme == "dark" else style.LIGHT)

    apply_theme(config.get("theme", "light"))
    window = MainWindow(store, config, save_config, apply_theme)
    window.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
