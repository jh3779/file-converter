"""find_soffice() 번들 경로 탐색 테스트 — macOS 배포(DEC-029) 추가 시,
Windows 전용(libreoffice/program/soffice.exe) 경로만 확인하고 macOS
번들 구조(libreoffice/LibreOffice.app/Contents/MacOS/soffice)를 놓쳐
실제 사용자 macOS 배포판에서 LibreOffice를 못 찾는 회귀가 날 뻔했다
(코드 리뷰 성격의 자체 점검으로 발견 — app/bundle.py의 engine_dir()
자동 탐색 시뮬레이션 중 확인)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.converters import office


class TestFindSofficeBundledPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patcher = patch("app.converters.office.engine_dir", return_value=self.tmp)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def _touch(self, rel_path: str) -> Path:
        p = self.tmp / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        return p

    def test_finds_windows_bundled_path(self):
        expected = self._touch("libreoffice/program/soffice.exe")
        self.assertEqual(office.find_soffice(), str(expected))

    def test_finds_macos_bundled_path(self):
        expected = self._touch("libreoffice/LibreOffice.app/Contents/MacOS/soffice")
        self.assertEqual(office.find_soffice(), str(expected))

    def test_no_bundle_falls_through_without_crashing(self):
        # PATH/기본 후보 경로에 실제로 없을 수도 있으므로 예외 없이 None 또는
        # 문자열을 반환하는지만 확인한다(크래시 방지가 핵심 — 실제 값은 환경 의존).
        try:
            office.find_soffice()
        except Exception as e:
            self.fail(f"find_soffice()가 예외를 던짐: {e}")


if __name__ == "__main__":
    unittest.main()
