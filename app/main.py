"""엔트리포인트: python -m app.main"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import tokens
from .ui.main_window import MainWindow


def pick_tokens(app: QApplication) -> dict:
    scheme = app.styleHints().colorScheme()
    return tokens.DARK if scheme == Qt.ColorScheme.Dark else tokens.LIGHT


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("file-converter")
    t = pick_tokens(app)
    app.setStyleSheet(tokens.build_qss(t))
    win = MainWindow(t)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
