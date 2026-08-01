"""FileRow 행 동작 테스트 — 지원 안 되는 파일의 제거(✕) 버튼.

실사용 테스터 리포트: "지원 안되는 파일 올리고 변환 시도한 후에 막히면
x버튼 클릭해도 안없어지더라". 재현: FileRow.__init__이 지원 안 되는
파일에 대해 self.setEnabled(False)로 행 전체를 비활성화했는데, Qt에서는
부모가 비활성화되면 이후 remove_btn.setEnabled(True)를 호출해도
효과가 없다(자식의 실질 활성 상태는 부모 상태와 AND로 결합됨) — 그래서
버튼은 보이지만 클릭이 전달되지 않았다.
"""
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.models import FileItem
from app.tokens import LIGHT as TOKENS
from app.ui.main_window import FileRow

_app = QApplication.instance() or QApplication([])


class TestFileRowRemove(unittest.TestCase):
    def test_remove_button_stays_clickable_for_unsupported_file(self):
        item = FileItem(id=1, source=Path("test.zip"), source_fmt="zip", target_fmt=None)
        removed = []
        row = FileRow(item, TOKENS, lambda item_id: removed.append(item_id), lambda: None)

        self.assertTrue(row.remove_btn.isEnabled())  # 부모(row) 비활성 상태에 가려지지 않아야 함

        row.remove_btn.click()
        self.assertEqual(removed, [1])

    def test_supported_file_row_unaffected(self):
        item = FileItem(id=2, source=Path("test.docx"), source_fmt="docx", target_fmt=None)
        row = FileRow(item, TOKENS, lambda item_id: None, lambda: None)
        self.assertTrue(row.isEnabled())
        self.assertTrue(row.remove_btn.isEnabled())


if __name__ == "__main__":
    unittest.main()
