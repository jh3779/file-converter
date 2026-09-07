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

from app import converters, i18n
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


class TestFileRowRetranslate(unittest.TestCase):
    """PR #122 코드 리뷰(Codex) 지적 재현: 감지된 영상(@video)의 fmt_label은
    _display_fmt()로 언어별 문자열("영상"/"Video")을 쓰는데, retranslate()가
    supported() 분기에서 fmt_label을 다시 계산하지 않아 언어 전환 후에도
    이전 언어 라벨이 남아있었다. 일반 확장자 포맷(예: docx → "DOCX")은
    항상 대문자라 언어와 무관해서 지금까지 드러나지 않았던 문제."""

    def setUp(self):
        self._orig_lang_pref = i18n.saved_pref()

    def tearDown(self):
        i18n.set_lang(self._orig_lang_pref or None)

    def test_detected_video_label_updates_on_language_switch_unlocked(self):
        item = FileItem(id=1, source=Path("26.09.06"),
                         source_fmt=converters.content_video_key(), target_fmt="mp4")
        i18n.set_lang("ko")
        row = FileRow(item, TOKENS, lambda item_id: None, lambda: None)
        self.assertEqual(row.fmt_label.text(), "영상 →")

        i18n.set_lang("en")
        row.retranslate()
        self.assertEqual(row.fmt_label.text(), "Video →")

    def test_detected_video_label_updates_on_language_switch_locked(self):
        item = FileItem(id=2, source=Path("26.09.07"),
                         source_fmt=converters.content_video_key(), target_fmt="mp4")
        i18n.set_lang("ko")
        row = FileRow(item, TOKENS, lambda item_id: None, lambda: None)
        row.set_locked(True)
        self.assertEqual(row.fmt_label.text(), "영상 → MP4")

        i18n.set_lang("en")
        row.retranslate()
        self.assertEqual(row.fmt_label.text(), "Video → MP4")


if __name__ == "__main__":
    unittest.main()
