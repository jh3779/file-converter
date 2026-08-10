"""결과 오버레이가 저해상도 창에서 스크롤되는지 테스트 — 외부 QA 피드백
(QA(e), UI 해상도/스크롤).

재현: 실패 항목이 여러 개(특히 파일명이 길어 여러 줄로 접히는 경우)면
결과 카드의 자연스러운 높이가 기본 최소 창 크기(640×480)보다 커질 수
있었다(직접 측정: 긴 파일명 5개 기준 자연 높이 536px > 480px). 카드
내용이 스크롤 없이 고정 레이아웃이었을 때는 Qt가 라벨 공간을 압축해
넣거나(가독성 저하) 최악의 경우 "확인"/"폴더 열기" 버튼이 창 밖으로
밀려나 결과 창을 닫을 방법이 없어질 위험이 있었다. 제목~저장 위치
구간만 QScrollArea로 감싸고 버튼 행은 스크롤 밖에 고정해, 창이 작아도
버튼은 항상 보이고 내용은 스크롤로 전부 접근 가능하도록 수정했다.
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QScrollArea

from app import i18n, tokens
from app.models import FileItem, ItemState
from app.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _failed_item(item_id: int, name: str) -> FileItem:
    it = FileItem(id=item_id, source=Path(f"{name}.docx"), source_fmt="docx", target_fmt="pdf")
    it.state = ItemState.FAILED
    it.error_key = "err.corrupted"
    return it


class TestResultOverlayScroll(unittest.TestCase):
    def setUp(self):
        self._orig_lang_pref = i18n.saved_pref()
        i18n.set_lang("ko")
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        i18n.set_lang(self._orig_lang_pref or None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_result_card_content_is_wrapped_in_scroll_area(self):
        win = MainWindow(tokens.LIGHT)
        self.assertIsInstance(win.result_scroll, QScrollArea)
        # 버튼 행("확인"/"폴더 열기")은 스크롤 영역 바깥의 result_card
        # 레이아웃에 직접 있어야 한다 — 스크롤 안에 있으면 스크롤을 끝까지
        # 내리지 않는 한 버튼이 안 보일 수 있다.
        self.assertNotEqual(win.result_ok_btn.parentWidget(), win.result_scroll.widget())

    def test_ok_button_stays_within_small_window_with_many_long_failures(self):
        """긴 파일명 실패 항목 여러 개로 카드의 자연 높이가 기본 최소
        창(640×480)보다 커지는 상황을 재현 — "확인" 버튼이 항상 창 안에
        있어야 한다(스크롤 없이는 창 밖으로 밀려날 수 있었음)."""
        win = MainWindow(tokens.LIGHT)
        win.resize(640, 480)
        win.show()
        win.items = [
            _failed_item(i, "아주아주아주긴한글파일이름_보고서_최종_수정본_v3_검토완료_" + str(i))
            for i in range(1, 6)
        ]
        win.rows = {}
        win._show_result()
        _app.processEvents()

        # 스크롤 없는 자연(unconstrained) 콘텐츠 높이가 실제로 스크롤
        # 영역의 상한보다 커야 이 테스트가 의미가 있다 — result_card 자체의
        # sizeHint는 이미 스크롤 상한으로 제한돼 있어(수정 후 의도된 동작)
        # 비교 대상이 될 수 없다.
        natural_content_height = win.result_scroll.widget().sizeHint().height()
        self.assertGreater(natural_content_height, win.result_scroll.maximumHeight(),
                            "이 시나리오가 스크롤 상한보다 큰 콘텐츠를 만들지 못함 — 테스트 데이터 조정 필요")

        btn_bottom = win.result_ok_btn.mapTo(win, win.result_ok_btn.rect().bottomLeft()).y()
        self.assertLessEqual(btn_bottom, win.height())

    def test_scroll_engages_instead_of_squeezing_labels(self):
        """스크롤 영역이 실제로 스크롤 가능해야 한다(뷰포트보다 내용이
        커야 함) — 그리고 라벨 텍스트는 실제 배치 폭 기준으로 잘리지
        않아야 한다(Qt가 라벨을 sizeHint 이하로 압축해 글자를 잘라내는
        대신 스크롤바를 쓰는지 확인)."""
        win = MainWindow(tokens.LIGHT)
        win.resize(640, 480)
        win.show()
        win.items = [
            _failed_item(i, "아주아주아주긴한글파일이름_보고서_최종_수정본_v3_검토완료_" + str(i))
            for i in range(1, 6)
        ]
        win.rows = {}
        win._show_result()
        _app.processEvents()

        scrollbar = win.result_scroll.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0, "스크롤이 전혀 활성화되지 않음")

        for i in range(win.result_fails.count()):
            lbl = win.result_fails.itemAt(i).widget()
            required = lbl.heightForWidth(lbl.width())
            self.assertGreaterEqual(lbl.height(), required,
                                     f"실패 항목 라벨 {i}의 텍스트가 잘림(할당 {lbl.height()} < 필요 {required})")


if __name__ == "__main__":
    unittest.main()
