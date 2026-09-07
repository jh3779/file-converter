"""appdata.resolve()의 타임아웃 동작 테스트 — 실사용 보고: 회사 로밍
프로필·OneDrive 등으로 AppData가 네트워크 경로에 리다이렉트돼 있으면,
그 네트워크가 응답 없을 때 mkdir()가 OS 타임아웃까지(수십 초~수 분)
아무 예외도 없이 그냥 멈출 수 있었다. logging_setup.setup()·History()
둘 다 메인 스레드에서, 앱 창이 뜨기도 전에 이 경로를 만들다 걸려서
프로세스는 살아있는데(작업 관리자엔 보임) CPU·디스크 사용률은 0%인 채로
창이 영원히 안 뜨는 것처럼 보였다.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app import appdata

_app = QApplication.instance() or QApplication([])


class TestAppDataResolveTimeout(unittest.TestCase):
    def test_resolve_returns_path_quickly_on_local_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "AppData"
            with patch("app.appdata.QStandardPaths.writableLocation", return_value=str(fake)):
                start = time.monotonic()
                result = appdata.resolve(timeout=2.0)
                elapsed = time.monotonic() - start
            self.assertEqual(result, fake)
            self.assertTrue(fake.is_dir())
            self.assertLess(elapsed, 1.0, "로컬 디스크는 즉시 끝나야 함")

    def test_resolve_gives_up_after_timeout_when_mkdir_hangs(self):
        """네트워크로 리다이렉트된 AppData가 응답 없을 때를 재현 —
        mkdir()가 timeout보다 오래 걸리면 resolve()는 그 mkdir이 끝나길
        기다리지 않고 timeout 안에 None으로 돌아와야 한다(데몬 스레드에
        안 걸림 — 실제 네트워크 호출은 백그라운드에서 나중에 끝나거나
        영영 안 끝나도 무방)."""
        def _hanging_mkdir(self, *a, **k):
            time.sleep(2)  # 실제 네트워크 타임아웃(수십 초~분)을 짧게 흉내

        with patch("app.appdata.Path.mkdir", _hanging_mkdir):
            start = time.monotonic()
            result = appdata.resolve(timeout=0.3)
            elapsed = time.monotonic() - start
        self.assertIsNone(result)
        self.assertLess(elapsed, 1.0, "resolve()가 timeout 안에 돌아와야 함")

    def test_resolve_returns_none_on_permission_error(self):
        """기존 except OSError 동작(권한 없음 등)은 그대로 유지되는지 확인."""
        with patch("app.appdata.Path.mkdir", side_effect=PermissionError("denied")):
            result = appdata.resolve(timeout=1.0)
        self.assertIsNone(result)


class TestHistoryAndLoggingFallback(unittest.TestCase):
    def test_history_falls_back_to_memory_when_appdata_unavailable(self):
        from app.history import History

        with patch("app.history.appdata.resolve", return_value=None):
            hist = History()  # path=None → _db_path() → None → ":memory:" 폴백
            hist.add("test.docx", "pdf", "/tmp/test.pdf", True)
            entries = hist.list()
        self.assertEqual(len(entries), 1)
        hist.close()

    def test_logging_setup_does_not_raise_when_appdata_unavailable(self):
        from app import logging_setup

        with patch("app.logging_setup.appdata.resolve", return_value=None):
            logging_setup.setup()  # 예외를 던지면 이 테스트 자체가 실패한다


class TestMainWindowStartupDoesNotHang(unittest.TestCase):
    def test_main_window_construction_is_fast_when_appdata_unavailable(self):
        """이번에 실제로 보고된 증상의 재현·수정 확인: AppData가 응답
        없는 네트워크 경로일 때도 MainWindow 생성(즉 앱 창이 뜨기까지)이
        오래 걸리면 안 된다."""
        from app import tokens
        from app.ui.main_window import MainWindow

        with patch("app.history.appdata.resolve", return_value=None):
            start = time.monotonic()
            win = MainWindow(tokens.LIGHT)
            elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.0,
                         "AppData 해석이 안 돼도 MainWindow 생성은 빨라야 함(창이 떠야 함)")
        win.close()


if __name__ == "__main__":
    unittest.main()
