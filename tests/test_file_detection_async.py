"""FileItem 생성(콘텐츠 기반 영상 감지 포함)을 백그라운드로 미뤄 UI
스레드 블로킹을 막는 로직 테스트 — 정밀 검증에서 발견: 확장자만으로
지원 여부를 못 정하는 파일을 드롭/선택하면 FileItem.__post_init__이
ffprobe(최대 수십 초 타임아웃)를 Qt 메인 스레드에서 동기 실행해, 파일
하나만 드롭해도 그 시간만큼 창이 그대로 멈췄다(app/workers.py의
create_file_item_async·FileDetectionSignals, app/ui/main_window.py의
add_files 분기로 수정).
"""
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app import converters, tokens, update_check
from app.ui.main_window import MainWindow
from app.workers import FileDetectionSignals, create_file_item_async

_app = QApplication.instance() or QApplication([])


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _app.processEvents()
        if predicate():
            return True
    return False


class TestCreateFileItemAsync(unittest.TestCase):
    def tearDown(self):
        # is_content_detected_video()는 모듈 전역 lru_cache라(정밀 재검증
        # 지적) 이 테스트 파일이 쓴 경로가 다른 테스트 파일의 같은 리터럴
        # 경로와 우연히 겹칠 가능성을 방어적으로 차단한다.
        converters.is_content_detected_video.cache_clear()

    def test_dispatch_returns_before_slow_probe_completes(self):
        """create_file_item_async() 호출 자체는 느린 감지(모킹으로 재현)를
        기다리지 않고 즉시 반환해야 한다 — 이게 안 되면 호출한 스레드가
        그대로 블로킹된다(원래 버그)."""
        def slow_probe(src):
            time.sleep(0.3)
            return True

        signals = FileDetectionSignals()
        received = []
        signals.ready.connect(lambda item: received.append(item))

        with patch.object(converters, "_VIDEO_AVAILABLE", True), \
             patch("app.converters.video.can_convert_to_mp4", side_effect=slow_probe):
            start = time.monotonic()
            create_file_item_async(1, Path(tempfile.mkdtemp()) / "26.09.06", "06", signals)
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 0.1,
                             "create_file_item_async()가 감지를 기다리지 않고 바로 반환해야 함")
            self.assertTrue(_wait_for(lambda: len(received) == 1),
                             "백그라운드 감지 완료 신호가 제시간에 오지 않음")
        self.assertEqual(received[0].source_fmt, converters.content_video_key())

    def test_recognized_extension_item_created_without_probing(self):
        """이미 지원되는 확장자는 콘텐츠 감지를 아예 시도하지 않는다
        (FileItem.__post_init__의 기존 단락평가 — 이 속성이 create_file_item_async
        경유에서도 그대로 유지되는지 확인)."""
        signals = FileDetectionSignals()
        received = []
        signals.ready.connect(lambda item: received.append(item))

        with patch("app.converters.video.can_convert_to_mp4") as mock_probe:
            create_file_item_async(2, Path("report.docx"), "docx", signals)
            self.assertTrue(_wait_for(lambda: len(received) == 1))
            mock_probe.assert_not_called()
        self.assertEqual(received[0].source_fmt, "docx")


class TestAddFilesDoesNotBlockOnDetection(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # MainWindow가 켜져 있으면 백그라운드 스레드로 업데이트 확인을
        # 시작한다(DEC-022) — 이 테스트가 만드는 MainWindow 인스턴스들과
        # 무관한 동작이라 매번 끈 상태로 고정(test_ui_update_notice.py와
        # 같은 패턴).
        self._orig_update_check = update_check.is_enabled()
        update_check.set_enabled(False)

    def tearDown(self):
        update_check.set_enabled(self._orig_update_check)
        converters.is_content_detected_video.cache_clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unrecognized_extension_add_files_returns_immediately(self):
        win = MainWindow(tokens.LIGHT)
        src = self.tmp / "26.09.06"
        src.write_bytes(b"fake")

        def slow_probe(s):
            time.sleep(0.3)
            return True

        with patch.object(converters, "_VIDEO_AVAILABLE", True), \
             patch("app.converters.video.can_convert_to_mp4", side_effect=slow_probe):
            start = time.monotonic()
            win.add_files([src])
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 0.1,
                             "add_files()가 콘텐츠 감지를 기다리지 않고 즉시 반환해야 함"
                             "(UI 스레드 블로킹 방지)")
            self.assertEqual(len(win.rows), 0,
                              "감지가 끝나기 전엔 아직 행이 추가되지 않아야 함")

            self.assertTrue(_wait_for(lambda: len(win.rows) == 1),
                             "백그라운드 감지 완료 후 행이 제시간에 추가되지 않음")
        row = next(iter(win.rows.values()))
        self.assertEqual(row.item.source_fmt, converters.content_video_key())
        win.close()
        _app.processEvents()

    def test_recognized_extension_still_added_synchronously(self):
        """일반 지원 확장자는 지금까지처럼 add_files() 호출 안에서 바로
        행이 추가돼야 한다(회귀 방지 — 비동기 경로가 전체를 느리게
        만들면 안 됨)."""
        win = MainWindow(tokens.LIGHT)
        src = self.tmp / "문서.docx"
        src.write_text("dummy")

        win.add_files([src])
        self.assertEqual(len(win.rows), 1)
        win.close()
        _app.processEvents()


if __name__ == "__main__":
    unittest.main()
