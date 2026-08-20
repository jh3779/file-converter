"""기록 패널 — 정본: docs/03_screen_contract.md SCR-003.

main_window.py에 응집돼 있던 패널 구성·렌더링을 분리했다(구조 감사
후속 조치, result_panel.py와 대칭). 각 함수는 MainWindow 인스턴스(win)를
받아 그 위에 필요한 위젯을 속성으로 붙이거나 조작한다 — 테스트가
`win.hist_list`처럼 직접 접근하는 기존 방식을 그대로 유지하기 위해서다.
"""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..i18n import tr


def build(win, body_layout):
    win.history_panel = QFrame()
    win.history_panel.setObjectName("historyPanel")
    win.history_panel.setFixedWidth(260)
    hp = QVBoxLayout(win.history_panel)
    hp.setContentsMargins(12, 10, 12, 10)
    hp.setSpacing(6)
    hp_head = QHBoxLayout()
    win.hist_title = QLabel()
    win.hist_title.setStyleSheet("font-weight:700;font-size:13px;")
    hp_head.addWidget(win.hist_title, 1)
    win.hist_clear = QPushButton()
    win.hist_clear.setProperty("variant", "error")
    win.hist_clear.clicked.connect(win._confirm_clear_history)
    hp_head.addWidget(win.hist_clear)
    hp.addLayout(hp_head)
    win.hist_local = QLabel()
    win.hist_local.setObjectName("shield")
    win.hist_local.setWordWrap(True)
    hp.addWidget(win.hist_local)
    win.hist_list = QVBoxLayout()
    win.hist_list.setSpacing(4)
    hist_scroll_inner = QWidget()
    hist_scroll_inner.setLayout(win.hist_list)
    win.hist_scroll = QScrollArea()
    win.hist_scroll.setWidgetResizable(True)
    win.hist_scroll.setFrameShape(QFrame.NoFrame)
    win.hist_scroll.setWidget(hist_scroll_inner)
    hp.addWidget(win.hist_scroll, 1)
    win.history_panel.hide()
    body_layout.addWidget(win.history_panel)


def toggle(win):
    vis = not win.history_panel.isVisible()
    win.history_panel.setVisible(vis)
    if vis:
        reload(win)
        ensure_width(win)


def ensure_width(win):
    """기록 패널(고정폭 260px)을 열면 본문(파일 목록)에 남는 폭이
    줄어든다 — 창이 이미 최소 크기 근처면 FileRow의 콤보박스·제거
    버튼이 QListWidget 뷰포트 밖으로 밀려나 가로 스크롤 없이는 안
    보이거나 안 눌릴 수 있다(QA(e), 실측 확인: 640px 창에서 제거
    버튼이 뷰포트를 21px 넘어감). QListWidget은 아이템이 넘쳐도
    자신의 minimumSizeHint를 늘리지 않아(스크롤로 대신 처리하는 Qt
    기본 동작) 레이아웃 시스템이 이 부족분을 자동으로 감지해 창을
    넓혀주지 않는다 — 패널을 여는 시점에 지금 목록에 있는 항목들의
    실제 필요 폭을 직접 계산해 부족하면 그만큼만 넓힌다(사용자가
    이미 그보다 넓게 열어뒀으면 줄이지 않는다). 파일이 많아 목록에
    세로 스크롤바가 뜨면 그만큼 뷰포트가 더 좁아지는데(자동 리뷰로
    발견, 파일 15개로 재현 확인), 항상 스크롤바 폭만큼 여유를 둬서
    나중에 파일이 더 늘어나 스크롤바가 새로 나타나도 안전하다."""
    if not win.rows:
        return
    max_row_width = max(row.minimumSizeHint().width() for row in win.rows.values())
    scrollbar_width = win.list.verticalScrollBar().sizeHint().width()
    needed = win.history_panel.width() + max_row_width + scrollbar_width + 32
    if win.width() < needed:
        win.resize(needed, win.height())


def reload(win):
    while win.hist_list.count():
        w = win.hist_list.takeAt(0).widget()
        if w:
            w.deleteLater()
    entries = win.history.list()
    t = win.tokens
    if not entries:
        empty = QLabel(tr("history.empty"))
        empty.setObjectName("muted")
        win.hist_list.addWidget(empty)
    for e in entries:
        row = QFrame()
        row.setObjectName("fileRow")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 5, 8, 5)
        rl.setSpacing(6)
        mark = QLabel("✓" if e.success else "⚠")
        mark.setStyleSheet(f"color:{t['tertiary'] if e.success else t['error']};font-weight:700;")
        rl.addWidget(mark)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel(f"{e.source_name} → {e.target_fmt.upper()}")
        name.setStyleSheet("font-weight:600;font-size:11px;")
        meta_text = e.converted_at + ("" if e.success else " · " + tr("history.failed"))
        if e.success and not Path(e.output_path).exists():
            meta_text = tr("history.notfound")
        meta = QLabel(meta_text)
        meta.setStyleSheet(
            f'font-family:"Menlo","Consolas",monospace;font-size:9px;color:{t["onSurfaceVariant"]};')
        col.addWidget(name)
        col.addWidget(meta)
        rl.addLayout(col, 1)
        if e.success and Path(e.output_path).exists():
            open_btn = QPushButton("📂")
            open_btn.setProperty("variant", "icon")
            open_btn.setAccessibleName("open location")
            # PDF→이미지(DEC-025)처럼 결과물이 폴더면 그 폴더를 직접 연다.
            open_btn.clicked.connect(
                lambda _, p=e.output_path: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(Path(p) if Path(p).is_dir() else Path(p).parent))))
            rl.addWidget(open_btn)
        del_btn = QPushButton("🗑")
        del_btn.setProperty("variant", "icon")
        del_btn.setAccessibleName("delete entry")
        del_btn.clicked.connect(lambda _, i=e.id: (win.history.delete(i), reload(win)))
        rl.addWidget(del_btn)
        win.hist_list.addWidget(row)
    win.hist_list.addStretch(1)


def confirm_clear(win):
    if win._safe_dialog(tr("dlg.clear.title"), tr("dlg.clear.body"),
                         tr("cancel"), tr("dlg.clear.confirm")):
        win.history.clear()
        reload(win)
