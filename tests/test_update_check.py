"""업데이트 확인 — OQ-002 해소(DEC-022). 버전 비교·실패 시 안전 처리·
옵트인 설정 저장을 검증한다. 실제 네트워크 요청은 하지 않는다(오프라인
CI에서도 결정적으로 통과해야 함)."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import update_check


class TestVersionParsing(unittest.TestCase):
    def test_tuple_comparison_not_lexicographic(self):
        """문자열 비교였다면 "0.3.10" < "0.3.4"로 잘못 나온다 — 튜플 비교라야 함."""
        self.assertGreater(update_check._parse("0.3.10"), update_check._parse("0.3.4"))

    def test_v_prefix_ignored(self):
        self.assertEqual(update_check._parse("v0.3.4"), update_check._parse("0.3.4"))

    def test_major_version_bump(self):
        self.assertGreater(update_check._parse("1.0.0"), update_check._parse("0.99.99"))


class TestFetchLatestVersion(unittest.TestCase):
    def test_network_failure_returns_none_not_exception(self):
        """오프라인 등으로 요청 자체가 실패해도 예외를 밖으로 던지면 안 된다
        — 선택 기능의 실패가 필수 기능의 오류처럼 보이면 안 되므로."""
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("오프라인")):
            self.assertIsNone(update_check.fetch_latest_version())

    def test_empty_release_list_returns_none(self):
        import json
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.read.return_value = json.dumps([]).encode("utf-8")
        resp.__enter__.return_value = resp
        with patch("urllib.request.urlopen", return_value=resp):
            self.assertIsNone(update_check.fetch_latest_version())

    def test_malformed_json_returns_none(self):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.read.return_value = "이것은 JSON이 아님".encode("utf-8")
        resp.__enter__.return_value = resp
        with patch("urllib.request.urlopen", return_value=resp):
            self.assertIsNone(update_check.fetch_latest_version())

    def test_latest_tag_extracted(self):
        import json
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.read.return_value = json.dumps(
            [{"tag_name": "v9.9.9"}, {"tag_name": "v0.1.0"}]).encode("utf-8")
        resp.__enter__.return_value = resp
        with patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(update_check.fetch_latest_version(), "9.9.9")


class TestOptIn(unittest.TestCase):
    def setUp(self):
        # update_check._store()는 실제 앱과 같은 QSettings("file-converter",
        # "app")을 쓴다 — 로컬 실행 시 사용자의 실제 설정에 영향 없도록
        # 원래 값을 캡처해 tearDown에서 복원한다.
        self._orig = update_check.is_enabled()

    def tearDown(self):
        update_check.set_enabled(self._orig)

    def test_default_is_disabled(self):
        # 새 QSettings 키라 아직 세팅된 적 없다면 False가 기본값이어야 함(옵트인).
        store = update_check._store()
        store.remove("update_check_enabled")
        self.assertFalse(update_check.is_enabled())

    def test_toggle_persists(self):
        update_check.set_enabled(True)
        self.assertTrue(update_check.is_enabled())
        update_check.set_enabled(False)
        self.assertFalse(update_check.is_enabled())


if __name__ == "__main__":
    unittest.main()
