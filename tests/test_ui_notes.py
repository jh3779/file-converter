"""FileRow 단순화 고지 문구 테스트 — DEC-010(PDF/HWP→DOCX)·DEC-017(DOCX→HWP).

리뷰 지적(코드 리뷰): DOCX→HWP는 표 구조가 손실되는 신규 경로인데 변환 전
UI 고지가 기존 DEC-010 범위로 확장되지 않았음 — 보완 후 회귀 방지용.
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


class TestFormatNote(unittest.TestCase):
    def _note_for(self, source_fmt: str, target_fmt: str):
        item = FileItem(id=1, source=Path(f"test.{source_fmt}"),
                         source_fmt=source_fmt, target_fmt=target_fmt)
        row = FileRow(item, TOKENS, lambda i: None, lambda: None)
        row._update_note()
        return (not row.reason.isHidden()), row.reason.text()

    def test_docx_to_hwp_shows_table_flatten_note(self):
        visible, text = self._note_for("docx", "hwp")
        self.assertTrue(visible)
        self.assertIn("표", text)

    def test_pdf_to_docx_shows_layout_simplified_note(self):
        visible, text = self._note_for("pdf", "docx")
        self.assertTrue(visible)

    def test_hwp_to_docx_shows_layout_simplified_note(self):
        visible, text = self._note_for("hwp", "docx")
        self.assertTrue(visible)

    def test_docx_to_pdf_shows_no_note(self):
        visible, _ = self._note_for("docx", "pdf")
        self.assertFalse(visible)

    def test_hwp_to_pdf_shows_no_note(self):
        visible, _ = self._note_for("hwp", "pdf")
        self.assertFalse(visible)


if __name__ == "__main__":
    unittest.main()
