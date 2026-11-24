LIGHT = """
QWidget { background: #f5f7fa; color: #202938; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QDialog { background: #f5f7fa; }
QFrame#Sidebar { background: #ffffff; border-right: 1px solid #e2e7ef; }
QFrame#TopBar, QFrame#Composer { background: #ffffff; }
QListWidget { background: #ffffff; border: 0; outline: 0; }
QListWidget::item { padding: 9px 10px; border-radius: 7px; margin: 2px 5px; }
QListWidget::item:selected { background: #e8f1ff; color: #1456a0; }
QLineEdit, QTextEdit, QPlainTextEdit { background: #ffffff; border: 1px solid #d8e0ea; border-radius: 8px; padding: 8px; }
QPushButton { background: #ffffff; border: 1px solid #d8e0ea; border-radius: 8px; padding: 7px 12px; }
QPushButton:hover { background: #edf4ff; border-color: #9bbce8; }
QPushButton#Primary { background: #2463ad; color: white; border: 0; font-weight: 600; }
QPushButton#Primary:hover { background: #1c5598; }
QLabel#Muted { color: #78869a; }
QFrame#BubbleOut { background: #e4efff; border-radius: 12px; }
QFrame#BubbleIn { background: #ffffff; border: 1px solid #e5eaf1; border-radius: 12px; }
QHeaderView::section { background: #edf1f6; padding: 7px; border: 0; }
QTableWidget { background: white; border: 1px solid #e2e7ef; border-radius: 8px; gridline-color: #edf0f4; }
"""
DARK = """
QWidget { background: #171c24; color: #e7edf5; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QDialog { background: #171c24; }
QFrame#Sidebar { background: #1d2430; border-right: 1px solid #303a49; }
QFrame#TopBar, QFrame#Composer { background: #202936; }
QListWidget { background: #1d2430; border: 0; outline: 0; }
QListWidget::item { padding: 9px 10px; border-radius: 7px; margin: 2px 5px; }
QListWidget::item:selected { background: #293f5c; color: #d9eaff; }
QLineEdit, QTextEdit, QPlainTextEdit { background: #202936; border: 1px solid #3a4657; border-radius: 8px; padding: 8px; }
QPushButton { background: #263140; border: 1px solid #3a4657; border-radius: 8px; padding: 7px 12px; }
QPushButton:hover { background: #31445d; }
QPushButton#Primary { background: #286bb8; color: white; border: 0; font-weight: 600; }
QLabel#Muted { color: #9aa9bb; }
QFrame#BubbleOut { background: #263e5b; border-radius: 12px; }
QFrame#BubbleIn { background: #222c39; border: 1px solid #354254; border-radius: 12px; }
QHeaderView::section { background: #263140; padding: 7px; border: 0; }
QTableWidget { background: #202936; border: 1px solid #3a4657; border-radius: 8px; gridline-color: #303b4b; }
"""
