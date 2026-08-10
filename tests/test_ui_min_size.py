"""선언된 최소 창 크기가 실제 레이아웃 요구 크기를 충족하는지 테스트 —
외부 QA 피드백(QA(e), UI 해상도/스크롤).

재현: `MainWindow.setMinimumSize(640, 480)`로 선언해뒀지만, 정작
`drop_big`(드롭존 버튼)의 안내 문구(`drop.sub`, 지원 포맷 목록)가 한 줄
문자열이었다 — QPushButton은 자동 줄바꿈을 지원하지 않아(Qt 자체 제약)
이 한 줄이 698px나 필요했고, 그 결과 실제 레이아웃이 요구하는 최소 창
너비(735px)가 선언된 값(640px)보다 커졌다. 즉 "최소 크기"로 선언한
값보다 창이 실제로는 더 작아질 수 없었고, 그 커진 실제 최소값이
저해상도 화면 너비를 넘을 수 있었다. `drop.sub`를 세 줄로 나눠 각 줄의
필요 폭을 줄여 해소했다.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app import i18n, tokens
from app.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class TestDeclaredMinimumSizeMatchesLayout(unittest.TestCase):
    def setUp(self):
        self._orig_lang_pref = i18n.saved_pref()

    def tearDown(self):
        i18n.set_lang(self._orig_lang_pref or None)

    def test_declared_minimum_covers_actual_layout_requirement_ko(self):
        i18n.set_lang("ko")
        win = MainWindow(tokens.LIGHT)
        win.show()
        declared = win.minimumSize()
        required = win.minimumSizeHint()
        self.assertLessEqual(
            required.width(), declared.width(),
            f"실제 레이아웃 요구 너비({required.width()}px)가 선언된 최소 창 너비"
            f"({declared.width()}px)보다 큼 — 저해상도 화면에서 창이 선언값보다 커질 수 있음")

    def test_declared_minimum_covers_actual_layout_requirement_en(self):
        i18n.set_lang("en")
        win = MainWindow(tokens.LIGHT)
        win.show()
        declared = win.minimumSize()
        required = win.minimumSizeHint()
        self.assertLessEqual(required.width(), declared.width())

    def test_drop_sub_text_is_wrapped_into_multiple_lines(self):
        """QPushButton은 자동 줄바꿈을 안 하므로, 긴 포맷 목록은 명시적
        `\\n`으로 여러 줄로 나뉘어 있어야 한 줄이 창 폭을 넘기지 않는다."""
        i18n.set_lang("ko")
        win = MainWindow(tokens.LIGHT)
        win.show()
        fm = win.drop_big.fontMetrics()
        for line in win.drop_big.text().split("\n"):
            self.assertLess(fm.horizontalAdvance(line), 500,
                             f"drop_big의 한 줄이 너무 넓음({fm.horizontalAdvance(line)}px): {line!r}")


if __name__ == "__main__":
    unittest.main()
