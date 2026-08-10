"""기록(History) 패널 실시간 동기화 테스트 — 외부 QA 피드백.

재현: 기록 패널을 열어둔 채로 파일을 변환하면 새 항목이 바로 안 뜨고,
패널을 껐다 켜야만(_toggle_history가 그때만 _reload_history를 부름) 보였다.
원인: _on_done/_on_failed가 history.add()만 하고, 이미 열려 있는 패널을
새로고침하지 않았다.
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app import i18n, tokens
from app.history import History
from app.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _hist_list_texts(win) -> list[str]:
    """hist_list 레이아웃에 실제로 보이는 라벨 텍스트를 전부 모은다.
    빈 상태(_reload_history)는 QLabel을 항목에 바로 넣고, 항목이 있을 때는
    QFrame 행 안에 QLabel이 자식으로 들어간다 — 둘 다 잡아야 한다(처음엔
    findChildren만 써서 빈 상태 라벨 자신을 놓치는 버그가 있었음)."""
    texts = []
    for i in range(win.hist_list.count()):
        item = win.hist_list.itemAt(i)
        w = item.widget() if item else None
        if isinstance(w, QLabel):
            texts.append(w.text())
        elif w:
            texts.extend(lbl.text() for lbl in w.findChildren(QLabel))
    return texts


class TestHistoryPanelLiveRefresh(unittest.TestCase):
    def setUp(self):
        # tr()은 시스템 로케일을 따른다(DEC-009) — CI 러너 로케일에 좌우되지
        # 않도록 언어를 한국어로 고정한다(tests/test_ui_notes.py와 같은 이유).
        self._orig_lang_pref = i18n.saved_pref()
        i18n.set_lang("ko")
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        i18n.set_lang(self._orig_lang_pref or None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _window(self) -> MainWindow:
        win = MainWindow(tokens.LIGHT)
        win.history = History(self.tmp / "history.db")  # 실제 앱 데이터 오염 방지
        # QWidget.isVisible()은 조상 체인 전체가 보여야 True다 — 최상위
        # 창을 show() 하지 않으면 history_panel.setVisible(True)를 호출해도
        # isVisible()이 계속 False로 나와(offscreen 플랫폼에서도 동일)
        # _record_history의 "패널이 열려 있으면 새로고침" 분기를 검증할 수
        # 없다.
        win.show()
        return win

    def test_new_entry_appears_while_panel_already_open(self):
        win = self._window()
        win._toggle_history()  # 패널을 켠 채로 시작
        self.assertTrue(win.history_panel.isVisible())
        self.assertIn("아직 변환 기록이 없습니다", _hist_list_texts(win))

        win._record_history("문서.docx", "pdf", "/tmp/out.pdf", True)

        texts = _hist_list_texts(win)
        self.assertNotIn("아직 변환 기록이 없습니다", texts)
        self.assertTrue(any("문서.docx" in t for t in texts))

    def test_failed_entry_also_refreshes_open_panel(self):
        win = self._window()
        win._toggle_history()
        win._record_history("깨진파일.zip", "", "", False)
        texts = _hist_list_texts(win)
        self.assertTrue(any("깨진파일.zip" in t for t in texts))

    def test_entry_saved_even_when_panel_closed(self):
        """패널이 닫혀 있을 때는 새로고침(위젯 재구성)까지 할 필요는
        없지만, 기록 자체는 항상 저장돼야 한다(다음에 열 때 보이도록)."""
        win = self._window()
        self.assertFalse(win.history_panel.isVisible())
        win._record_history("문서.docx", "pdf", "/tmp/out.pdf", True)
        self.assertEqual(len(win.history.list()), 1)


if __name__ == "__main__":
    unittest.main()
