"""결과 오버레이의 저장 위치 안내 테스트 — 외부 QA 피드백(DEC-042).

재현: 변환 완료 후 결과 오버레이에 "N개 파일을 원본 폴더에 저장했습니다"
같은 문구는 있었지만 실제 경로는 어디에도 안 보였다(폴더 열기 버튼을
누르거나 최근 기록 창을 열어야만 확인 가능했음). _show_result가 완료된
항목들의 저장 폴더를 중복 없이 최대 3곳까지 직접 보여주도록 수정했다.
"""
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app import i18n, tokens
from app.models import FileItem, ItemState
from app.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _location_texts(win) -> list[str]:
    texts = []
    for i in range(win.result_locations.count()):
        item = win.result_locations.itemAt(i)
        w = item.widget() if item else None
        if isinstance(w, QLabel):
            texts.append(w.text())
    return texts


def _done_item(item_id: int, output: Path) -> FileItem:
    it = FileItem(id=item_id, source=Path(f"src{item_id}.docx"), source_fmt="docx", target_fmt="pdf")
    it.state = ItemState.DONE
    it.output = output
    return it


class TestResultLocationNotice(unittest.TestCase):
    def setUp(self):
        self._orig_lang_pref = i18n.saved_pref()
        i18n.set_lang("ko")

    def tearDown(self):
        i18n.set_lang(self._orig_lang_pref or None)

    def _window(self, items):
        win = MainWindow(tokens.LIGHT)
        win.items = items
        win.rows = {}
        win.show()
        win._show_result()
        return win

    def test_single_file_shows_its_folder(self):
        win = self._window([_done_item(1, Path("/tmp/a/out.pdf"))])
        self.assertEqual(_location_texts(win), ["📂 /tmp/a"])

    def test_duplicate_folders_deduplicated(self):
        items = [_done_item(1, Path("/tmp/a/out1.pdf")), _done_item(2, Path("/tmp/a/out2.pdf"))]
        win = self._window(items)
        self.assertEqual(_location_texts(win), ["📂 /tmp/a"])

    def test_more_than_three_folders_capped_with_summary(self):
        items = [_done_item(i, Path(f"/tmp/{c}/out.pdf")) for i, c in enumerate("abcd")]
        win = self._window(items)
        texts = _location_texts(win)
        self.assertEqual(texts[:3], ["📂 /tmp/a", "📂 /tmp/b", "📂 /tmp/c"])
        self.assertEqual(win.result_locations.count(), 4)  # 3개 + 요약 1개

    def test_directory_output_shown_as_is_not_its_parent(self):
        """PDF→이미지(DEC-025)처럼 결과물 자체가 폴더면 그 폴더를 보여줘야
        한다(open_folder_btn과 같은 원칙) — 부모 폴더가 아니라."""
        out_dir = Path("/tmp/x/out")
        out_dir.mkdir(parents=True, exist_ok=True)
        win = self._window([_done_item(1, out_dir)])
        self.assertEqual(_location_texts(win), [f"📂 {out_dir}"])

    def test_no_done_items_shows_nothing(self):
        it = FileItem(id=1, source=Path("bad.zip"), source_fmt="zip", target_fmt=None)
        it.state = ItemState.FAILED
        it.error_key = "err.engine"
        win = self._window([it])
        self.assertEqual(_location_texts(win), [])


if __name__ == "__main__":
    unittest.main()
