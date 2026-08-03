"""업데이트 확인 UI 통합 테스트 — 옵트인 토글 + 알림 표시(OQ-002, DEC-022)."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app import tokens, update_check
from app.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class TestUpdateNotice(unittest.TestCase):
    def setUp(self):
        self._orig = update_check.is_enabled()
        update_check.set_enabled(False)  # 각 테스트는 꺼진 상태에서 시작

    def tearDown(self):
        update_check.set_enabled(self._orig)

    def test_notice_hidden_by_default(self):
        win = MainWindow(tokens.LIGHT)
        self.assertTrue(win.update_notice.isHidden())

    def test_found_shows_notice_with_version(self):
        win = MainWindow(tokens.LIGHT)
        win._on_update_found("9.9.9")
        self.assertFalse(win.update_notice.isHidden())
        self.assertIn("9.9.9", win.update_notice.text())

    def test_no_update_keeps_notice_hidden(self):
        win = MainWindow(tokens.LIGHT)
        win._on_update_found("")
        self.assertTrue(win.update_notice.isHidden())

    def test_toggle_off_hides_notice_and_persists_setting(self):
        win = MainWindow(tokens.LIGHT)
        win._on_update_found("9.9.9")
        self.assertFalse(win.update_notice.isHidden())
        win._toggle_update_check(False)
        self.assertTrue(win.update_notice.isHidden())
        self.assertFalse(update_check.is_enabled())

    def test_toggle_on_persists_setting_without_real_network_call(self):
        # 토글을 켜면 즉시 백그라운드 스레드로 확인을 시작한다 — 테스트에서는
        # 실제 네트워크를 타지 않도록 fetch_latest_version을 목(mock)한다.
        with patch("app.update_check.fetch_latest_version", return_value=None):
            win = MainWindow(tokens.LIGHT)
            win._toggle_update_check(True)
        self.assertTrue(update_check.is_enabled())


if __name__ == "__main__":
    unittest.main()
