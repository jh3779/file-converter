"""History SQLite 연결 정리(close()) 테스트 — production audit F-07.

재현: History가 sqlite3 연결을 열기만 하고 닫는 방법이 없어, 앱 종료
후에도 연결이 열린 채로 남아(ResourceWarning: unclosed database) 파일
디스크립터가 새는 문제가 있었다.
"""
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.history import History


class TestHistoryClose(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_close_closes_the_underlying_connection(self):
        hist = History(self.tmp / "history.db")
        hist.add("a.docx", "pdf", "/tmp/a.pdf", True)
        hist.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            hist.list()


if __name__ == "__main__":
    unittest.main()
