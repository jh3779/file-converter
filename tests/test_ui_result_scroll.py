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


# 플랫폼마다 오프스크린 폰트 렌더링 폭이 달라(CI Linux vs 로컬 macOS) 실제
# 줄바꿈 수·라벨 높이가 갈린다 — 로컬에서 재현된 문제가 CI(더 좁은 대체
# 폰트)에서는 재현 안 될 수 있음을 실측 확인(처음 버전은 파일명이 짧아
# CI에서만 스크롤이 안 필요해져 실패했음). 여러 줄로 감싸질 만큼 충분히
# 길게 반복해 어떤 폰트 폭에서도 640×480보다 자연 높이가 커지도록 마진을
# 크게 둔다.
_VERY_LONG_NAME = "아주아주아주긴한글파일이름_보고서_최종_수정본_v3_검토완료_전자결재승인대기중_담당자확인요망" * 2


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
            _failed_item(i, _VERY_LONG_NAME + str(i))
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
            _failed_item(i, _VERY_LONG_NAME + str(i))
            for i in range(1, 6)
        ]
        win.rows = {}
        win._show_result()
        _app.processEvents()

        # 스크롤 최대 높이를 아주 작게 강제한다 — 플랫폼마다 기본 폰트
        # 렌더링 폭/높이가 달라(예: CI Linux 오프스크린 폰트가 로컬 macOS
        # 폰트보다 좁음) "이 5개 항목이 640×480에서 자연스럽게 넘치는지"는
        # 환경에 따라 달라질 수 있다(실제로 CI에서 이 값이 달라 스크롤이
        # 전혀 필요 없어져 테스트가 실패한 것을 발견) — 스크롤이 필요한
        # 상황 자체를 결정적으로 만들어 환경 의존성을 없앤다.
        win.result_scroll.setMaximumHeight(50)
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
