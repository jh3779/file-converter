"""드롭존 안내 문구(drop.sub)가 영상 변환 미지원 환경(FFmpeg 미번들,
macOS — DEC-029)에서도 항상 영상을 광고하던 문제(production audit F-04).

"가능한 것만 노출한다"(C-03, converters.TARGETS 원칙)는 실제 변환 대상
목록에는 이미 적용되어 있었지만, 드롭존 정적 문구는 플랫폼과 무관하게
항상 "AVI MOV MKV 등 영상"을 보여줘 UI 카피와 실제 지원 범위가
어긋났다 — `converters.supported("avi")`로 런타임에 판단해 영상 미지원
환경에서는 별도 문구(`drop.sub_novideo`)를 쓰도록 분기했다.
"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app import i18n, tokens
from app.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class TestDropSubTextReflectsVideoSupport(unittest.TestCase):
    def setUp(self):
        self._orig_lang_pref = i18n.saved_pref()
        i18n.set_lang("ko")

    def tearDown(self):
        i18n.set_lang(self._orig_lang_pref or None)

    def test_drop_sub_advertises_video_when_supported(self):
        with patch("app.ui.main_window.converters.supported", return_value=True):
            win = MainWindow(tokens.LIGHT)
            self.assertIn("영상", win.drop_big.text())

    def test_drop_sub_omits_video_when_unsupported(self):
        with patch("app.ui.main_window.converters.supported", return_value=False):
            win = MainWindow(tokens.LIGHT)
            self.assertNotIn("영상", win.drop_big.text())
            self.assertIn("이미지", win.drop_big.text())

    def test_drop_sub_omits_video_when_unsupported_en(self):
        i18n.set_lang("en")
        with patch("app.ui.main_window.converters.supported", return_value=False):
            win = MainWindow(tokens.LIGHT)
            self.assertNotIn("video", win.drop_big.text())
            self.assertIn("image", win.drop_big.text())


if __name__ == "__main__":
    unittest.main()
