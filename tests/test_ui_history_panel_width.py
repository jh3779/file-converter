"""기록 패널을 열면 파일 목록 항목이 잘리던 문제 테스트 — 외부 QA 피드백
(QA(e), UI 해상도/스크롤).

재현: 기록 패널(고정폭 260px)을 열면 본문(파일 목록)에 남는 폭이
줄어든다. 창이 이미 최소 크기(640×480) 근처면 FileRow의 콤보박스·제거
버튼이 QListWidget 뷰포트 밖으로 밀려나 가로 스크롤 없이는 안 보이거나
안 눌릴 수 있었다(실측: 640px 창에서 제거(✕) 버튼이 뷰포트를 21px
넘어감). QListWidget은 아이템이 넘쳐도 자신의 minimumSizeHint를 늘리지
않아(스크롤로 대신 처리하는 Qt 기본 동작) 레이아웃 시스템이 이 부족분을
자동으로 감지해 창을 넓혀주지 않는다 — 기록 패널을 여는 시점에 지금
목록에 있는 항목들의 실제 필요 폭을 직접 계산해 부족하면 창을 그만큼만
넓히도록 수정했다.

자동 리뷰(Codex)가 이어서 지적한 두 가지 갭도 재현·수정 후 회귀 테스트로
고정: (1) 패널을 먼저 열어둔 채(그때는 목록이 비어 있어 보정이 아무
일도 안 함) 파일을 나중에 추가하는 순서에서는 여전히 잘렸다 —
add_files()에서도 패널이 열려 있으면 다시 확인하도록 보완. (2) 파일이
많아 목록에 세로 스크롤바가 뜨면 뷰포트가 더 좁아지는데 필요 폭 계산에
스크롤바 폭이 빠져 있었다 — 항상 포함하도록 보완.
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app import i18n, tokens
from app.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class TestHistoryPanelDoesNotClipFileRow(unittest.TestCase):
    def setUp(self):
        self._orig_lang_pref = i18n.saved_pref()
        i18n.set_lang("ko")
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        i18n.set_lang(self._orig_lang_pref or None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _window_with_one_file(self):
        win = MainWindow(tokens.LIGHT)
        win.resize(640, 480)  # 선언된 최소 창 크기(가장 좁은 실사용 시나리오)
        win.show()
        src = self.tmp / "문서예시파일.docx"
        src.write_text("dummy")
        win.add_files([src])
        _app.processEvents()
        return win

    def test_remove_button_stays_within_list_viewport_after_opening_history(self):
        win = self._window_with_one_file()
        win._toggle_history()
        _app.processEvents()

        self.assertTrue(win.history_panel.isVisible())
        row = next(iter(win.rows.values()))
        remove_right = row.remove_btn.mapTo(win.list.viewport(), row.remove_btn.rect().bottomRight()).x()
        self.assertLessEqual(remove_right, win.list.viewport().width(),
                              "기록 패널을 연 뒤 파일 제거 버튼이 목록 뷰포트 밖으로 밀려남")

    def test_window_not_widened_when_history_panel_has_no_effect(self):
        """파일 목록이 비어 있으면(FileRow 자체가 없음) 넓힐 필요가 없다
        — 창 크기를 불필요하게 건드리지 않아야 한다."""
        win = MainWindow(tokens.LIGHT)
        win.resize(640, 480)
        win.show()
        before = win.size()
        win._toggle_history()
        _app.processEvents()
        self.assertEqual(win.size(), before)

    def test_remove_button_stays_within_viewport_when_history_opened_before_files_added(self):
        """자동 리뷰로 발견된 순서 문제: 기록 패널을 먼저 연 뒤(그때는
        목록이 비어 있어 보정이 아무 일도 안 함) 파일을 나중에 추가하면
        _toggle_history 쪽 보정만으로는 부족했다 — add_files에서도
        패널이 열려 있으면 다시 확인해야 한다."""
        win = MainWindow(tokens.LIGHT)
        win.resize(640, 480)
        win.show()
        win._toggle_history()
        _app.processEvents()
        self.assertTrue(win.history_panel.isVisible())

        src = self.tmp / "문서예시파일.docx"
        src.write_text("dummy")
        win.add_files([src])
        _app.processEvents()

        row = next(iter(win.rows.values()))
        remove_right = row.remove_btn.mapTo(win.list.viewport(), row.remove_btn.rect().bottomRight()).x()
        self.assertLessEqual(remove_right, win.list.viewport().width(),
                              "패널을 먼저 연 뒤 추가한 파일의 제거 버튼이 뷰포트 밖으로 밀려남")

    def test_remove_button_stays_within_viewport_with_vertical_scrollbar(self):
        """자동 리뷰로 발견된 계산 누락: 파일이 많아 목록에 세로
        스크롤바가 뜨면 뷰포트가 더 좁아지는데, 필요 폭 계산에 스크롤바
        폭이 빠져 있었다."""
        win = MainWindow(tokens.LIGHT)
        win.resize(640, 480)
        win.show()
        files = []
        for i in range(15):
            f = self.tmp / f"문서예시파일_{i}.docx"
            f.write_text("dummy")
            files.append(f)
        win.add_files(files)
        _app.processEvents()
        win._toggle_history()
        _app.processEvents()

        self.assertTrue(win.list.verticalScrollBar().isVisible(),
                         "이 테스트가 검증하려는 세로 스크롤바 자체가 안 뜸 — 파일 개수 조정 필요")
        worst = max(
            row.remove_btn.mapTo(win.list.viewport(), row.remove_btn.rect().bottomRight()).x()
            for row in win.rows.values())
        self.assertLessEqual(worst, win.list.viewport().width(),
                              "세로 스크롤바가 있을 때 제거 버튼이 뷰포트 밖으로 밀려남")


if __name__ == "__main__":
    unittest.main()
