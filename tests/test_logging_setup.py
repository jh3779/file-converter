"""logging_setup.setup() 실패 격리 테스트 — 정밀 검증 지적: 진단 로그
초기화가 예외 가드 없이 호출돼, AppData 쓰기 실패(권한 등) 시
MainWindow가 뜨기도 전에 앱 자체가 죽을 수 있었다."""
import logging
import logging.handlers
import unittest
from unittest.mock import patch

from app import logging_setup


class TestLoggingSetupFailureIsolation(unittest.TestCase):
    def tearDown(self):
        # setup()이 성공한 경우 루트 로거에 남긴 핸들러가 다른 테스트의
        # 로그 출력에 섞이지 않도록 정리.
        root = logging.getLogger()
        for h in list(root.handlers):
            if isinstance(h, logging.handlers.RotatingFileHandler):
                root.removeHandler(h)
                h.close()

    def test_setup_does_not_raise_when_log_path_unavailable(self):
        with patch.object(logging_setup, "_log_path", side_effect=OSError("permission denied")):
            logging_setup.setup()  # 예외를 던지면 이 테스트 자체가 실패한다

    def test_setup_succeeds_normally(self):
        logging_setup.setup()
        root = logging.getLogger()
        self.assertTrue(any(
            getattr(h, "baseFilename", "").endswith("app.log") for h in root.handlers
        ))


if __name__ == "__main__":
    unittest.main()
