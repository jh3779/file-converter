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
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app import appdata

_app = QApplication.instance() or QApplication([])


class TestAppDataResolveTimeout(unittest.TestCase):
    def setUp(self):
        # resolve()는 프로세스 생애 동안 결과를 캐시한다(MainWindow를
        # 대량으로 만드는 테스트 스위트에서 매번 새 스레드를 스폰하다가
        # CI에서 스레드 생성 자체가 멈추는 문제가 있었음) — 이 클래스는
        # 매 테스트마다 다른 mkdir 동작을 흉내내 실제 로직을 검증해야
        # 하므로, 캐시가 이전 테스트 결과를 들고 있지 않도록 초기화한다.
        appdata._reset_cache_for_tests()

    def tearDown(self):
        # 이 클래스의 테스트들은 실제 AppData가 아니라 임시 디렉터리로
        # 캐시를 채운다 — 그 디렉터리는 테스트가 끝나면(tempfile 컨텍스트
        # 종료) 삭제되므로, 캐시에 남겨두면 이후 다른 테스트 파일의
        # History()가 이미 지워진 경로로 sqlite3.connect()를 시도해 실패한다.
        # 다음 테스트가 진짜 AppData를 다시 해석하도록 캐시를 비운다.
        appdata._reset_cache_for_tests()

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

    def test_second_call_reuses_cached_result_without_spawning_new_thread(self):
        """CI에서 실제로 재현된 문제: MainWindow를 대량으로 생성하는
        테스트 스위트에서 매번 resolve()가 새 스레드를 스폰하면, 그
        스레드 생성 누적이 결국 CPython 내부 스레드 상태 락 경합으로
        스레드 생성 자체가 멈추는 지점까지 갈 수 있다(faulthandler로
        확보한 실제 CI 스택 트레이스로 확인). 첫 호출 뒤에는 스레드를
        새로 스폰하지 않고 캐시를 그대로 반환해야 한다."""
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "AppData"
            with patch("app.appdata.QStandardPaths.writableLocation", return_value=str(fake)):
                first = appdata.resolve(timeout=2.0)
            self.assertEqual(first, fake)

            with patch("app.appdata.threading.Thread") as mock_thread:
                second = appdata.resolve(timeout=2.0)
            mock_thread.assert_not_called()
        self.assertEqual(second, first)

    def test_timeout_does_not_permanently_cache_failure_when_thread_later_succeeds(self):
        """review 지적 반영 — 타임아웃(아직 안 끝남)을 "확정된 실패"로
        영구 캐시해버리면, logging_setup.setup()이 먼저 타임아웃된 뒤
        곧바로 History()가 호출될 때 실제로는 성공할 백그라운드 스레드의
        결과를 영영 못 받아 해당 세션 내내 기록이 :memory:로 손실될
        위험이 있었다. 첫 호출이 타임아웃돼도, 같은 스레드가 이어서
        돌다가 나중에 실제로 성공하면 다음 호출은 새 스레드를 스폰하지
        않고도 그 성공 결과를 받아야 한다."""
        orig_mkdir = Path.mkdir

        def _slow_mkdir(self, *args, **kwargs):
            time.sleep(0.4)
            return orig_mkdir(self, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "AppData"
            with patch("app.appdata.QStandardPaths.writableLocation", return_value=str(fake)), \
                 patch("app.appdata.Path.mkdir", _slow_mkdir), \
                 patch("app.appdata.threading.Thread", wraps=appdata.threading.Thread) as thread_spy:
                first = appdata.resolve(timeout=0.05)
                self.assertIsNone(first, "스레드가 아직 안 끝났으니 이번 호출은 None이어야 함")

                second = appdata.resolve(timeout=1.0)
                self.assertEqual(second, fake, "같은 스레드가 이어서 성공했으면 그 결과를 받아야 함")

                thread_spy.assert_called_once()  # 스레드는 첫 호출 때 딱 1개만 스폰돼야 함

    def test_stale_thread_from_earlier_generation_does_not_corrupt_later_result(self):
        """review 지적 반영 — `_resolve()` 클로저가 결과 그릇을 모듈 전역
        이름으로 참조하면, `_reset_cache_for_tests()`가 그 이름을 새 dict로
        갈아치운 뒤 이전(좀비) 스레드가 뒤늦게 끝나면서 그 시점에 바인딩된
        dict(=다른 세대의 결과 그릇)에 잘못 써버릴 수 있었다.

        `_cache`는 한 번 확정되면 이후 `_result`/`_thread_result`를 다시
        안 읽는 "래치(latch)" 구조라, `resolve()`의 반환값만으로는 이
        오염을 안정적으로 재현하기 어렵다(타이밍 경쟁이 필요하고, 대부분의
        경로에서 래치가 이미 우연히 막아준다 — 실제로 구버전 코드에
        타이밍을 넉넉히 준 검증을 돌려봐도 반환값 자체는 오염되지 않는
        것을 확인했다). 그래서 이 테스트는 반환값이 아니라 **결과 그릇
        객체 자체가 세대마다 물리적으로 분리되는지**를 직접 확인한다 —
        이게 바로 이 수정이 실제로 보장하는 것이고, 반환값 수준의 우연한
        안전망에 기대지 않고 근본적으로 격리됐는지 검증하는 방법이다."""
        orig_mkdir = Path.mkdir
        zombie_entered_mkdir = threading.Event()

        def _slow_mkdir_wrong_dir(self, *args, **kwargs):
            zombie_entered_mkdir.set()
            time.sleep(0.3)
            return orig_mkdir(self, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            stale_dir = Path(tmp) / "StaleAppData"
            with patch("app.appdata.QStandardPaths.writableLocation", return_value=str(stale_dir)), \
                 patch("app.appdata.Path.mkdir", _slow_mkdir_wrong_dir):
                first = appdata.resolve(timeout=0.05)
                self.assertIsNone(first, "느린 mkdir이라 이번 호출은 None이어야 함")
                self.assertTrue(zombie_entered_mkdir.wait(1.0), "좀비 스레드가 mkdir 호출까지 진행하지 못함")
                # 이 시점에 좀비 스레드는 이미 stale_dir을 base로 확정하고
                # (패치된) mkdir 안에서 잠들어 있다 — 아래에서 패치가
                # 풀려도 이미 진행 중인 호출엔 영향 없다.
                gen1_result = appdata._thread_result  # 좀비(1세대)가 쓸 결과 그릇을 미리 캡처

            appdata._reset_cache_for_tests()

            real_dir = Path(tmp) / "RealAppData"
            with patch("app.appdata.QStandardPaths.writableLocation", return_value=str(real_dir)):
                second = appdata.resolve(timeout=1.0)
            self.assertEqual(second, real_dir)

            gen2_result = appdata._thread_result  # 새 세대(2세대)의 결과 그릇
            self.assertIsNot(
                gen1_result, gen2_result,
                "세대마다 물리적으로 다른 결과 그릇을 써야 좀비 스레드가 서로 못 건드림")

            # 좀비 스레드가 실제로 완료될 때까지(0.3초+여유) 기다린 뒤,
            # 자기 그릇(gen1_result)에만 썼는지, 2세대의 그릇(gen2_result)은
            # 전혀 안 건드렸는지 직접 확인한다.
            time.sleep(0.4)
            self.assertEqual(gen1_result.get("path"), stale_dir,
                              "좀비 스레드도 결국 완료돼 자기 그릇엔 정상적으로 씀(대조군)")
            self.assertEqual(gen2_result.get("path"), real_dir,
                              "좀비 스레드의 뒤늦은 쓰기가 2세대의 그릇을 건드리면 안 됨")
            self.assertEqual(appdata.resolve(timeout=0.1), real_dir)


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
