"""엔트리포인트: python -m app.main"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import logging_setup, tokens
from .ui.main_window import MainWindow


def pick_tokens(app: QApplication) -> dict:
    scheme = app.styleHints().colorScheme()
    return tokens.DARK if scheme == Qt.ColorScheme.Dark else tokens.LIGHT


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("file-converter")
    # QStandardPaths.AppDataLocation은 applicationName에 따라 갈리므로
    # (history.py의 _db_path()와 같은 원칙), 이름을 정한 뒤에 초기화한다.
    logging_setup.setup()
    t = pick_tokens(app)
    app.setStyleSheet(tokens.build_qss(t))
    win = MainWindow(t)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
