"""결과 오버레이 — 정본: docs/03_screen_contract.md SCR-002, DEC-008.

main_window.py에 응집돼 있던 오버레이 구성·렌더링을 분리했다(구조 감사
후속 조치, history_panel.py와 대칭). 각 함수는 MainWindow 인스턴스(win)를
받아 그 위에 필요한 위젯을 속성으로 붙이거나 조작한다 — 테스트가
`win.result_scroll`처럼 직접 접근하는 기존 방식을 그대로 유지하기 위해서다.
"""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..i18n import tr
from ..models import ItemState


def build(win, central):
    t = win.tokens
    win.overlay = QFrame(central)
    win.overlay.setObjectName("overlay")
    win.overlay.setStyleSheet("QFrame#overlay{background:rgba(0,0,0,0.35);}")
    ov = QVBoxLayout(win.overlay)
    ov.setAlignment(Qt.AlignCenter)
    win.result_card = QFrame()
    win.result_card.setObjectName("resultCard")
    win.result_card.setStyleSheet(
        f"QFrame#resultCard{{background:{t['surfaceContainerLow']};border-radius:16px;}}"
        "QFrame#resultCard QLabel{background:transparent;}")
    win.result_card.setFixedWidth(360)
    rc = QVBoxLayout(win.result_card)
    rc.setContentsMargins(18, 16, 18, 14)
    rc.setSpacing(8)

    # 내용(제목~저장 위치)만 스크롤 가능하게 감싸고 버튼 행은 스크롤 밖에
    # 고정한다 — 실패 목록·저장 위치가 늘어나 카드 전체 높이가 저해상도
    # 창보다 커지면, 스크롤 없이는 "확인"/"폴더 열기" 버튼까지 화면 밖으로
    # 밀려나 결과 창을 닫을 방법이 없어지는 문제가 있었다(QA(e), 재현
    # 확인 후 수정).
    win.result_scroll = QScrollArea()
    win.result_scroll.setWidgetResizable(True)
    win.result_scroll.setFrameShape(QFrame.NoFrame)
    win.result_scroll.setStyleSheet("background:transparent;")
    result_content = QWidget()
    result_content.setStyleSheet("background:transparent;")
    rcc = QVBoxLayout(result_content)
    rcc.setContentsMargins(0, 0, 0, 0)
    rcc.setSpacing(8)
    win.result_title = QLabel()
    win.result_title.setStyleSheet("font-weight:700;font-size:14px;")
    win.result_counts = QLabel()
    win.result_counts.setStyleSheet('font-family:"Menlo","Consolas",monospace;font-size:12px;')
    win.result_fails = QVBoxLayout()
    win.result_note = QLabel()
    win.result_note.setObjectName("muted")
    win.result_note.setWordWrap(True)
    win.result_locations = QVBoxLayout()  # 저장 위치 안내(외부 QA 피드백)
    win.result_locations.setSpacing(2)
    rcc.addWidget(win.result_title)
    rcc.addWidget(win.result_counts)
    rcc.addLayout(win.result_fails)
    rcc.addWidget(win.result_note)
    rcc.addLayout(win.result_locations)
    win.result_scroll.setWidget(result_content)
    rc.addWidget(win.result_scroll)

    btns = QHBoxLayout()
    btns.addStretch(1)
    win.open_folder_btn = QPushButton()
    win.open_folder_btn.setProperty("variant", "text")
    win.open_folder_btn.clicked.connect(win._open_result_folder)
    win.result_ok_btn = QPushButton()
    win.result_ok_btn.setProperty("variant", "filled")
    win.result_ok_btn.clicked.connect(win._dismiss_result)
    btns.addWidget(win.open_folder_btn)
    btns.addWidget(win.result_ok_btn)
    rc.addLayout(btns)
    ov.addWidget(win.result_card)
    win.overlay.hide()


def resize(win):
    """MainWindow.resizeEvent에서 호출 — 오버레이 지오메트리·스크롤 높이 재계산."""
    win.overlay.setGeometry(win.centralWidget().rect())
    # 결과 카드 안 스크롤 영역의 최대 높이를 창 크기에 맞춰 다시 계산한다
    # — 카드 자체는 고정 높이가 아니라 내용에 맞춰 커지므로, 이 상한이
    # 없으면 저해상도 창에서 카드가 창보다 커져 버튼이 잘릴 수 있다.
    # 160은 카드 여백(rc 상하 margin 30)·제목·개수 라벨·버튼 행 높이를
    # 실측으로 감안한 여유값 — 정확한 각 위젯 높이를 매번 합산하는
    # 대신 저해상도(1280x720급)에서도 버튼이 항상 보이는지 실제로
    # 확인한 값을 씀.
    reserve = 160
    win.result_scroll.setMaximumHeight(max(120, win.centralWidget().height() - reserve))


def show_result(win):
    done = [it for it in win.items if it.state == ItemState.DONE]
    failed = [it for it in win.items if it.state == ItemState.FAILED]
    t = win.tokens
    if not failed:
        win.result_title.setText("✅ " + tr("result.allsuccess"))
    elif done:
        win.result_title.setText("⚠️ " + tr("result.partial"))
    else:
        win.result_title.setText("❌ " + tr("result.allfail"))
    ok_color = t["tertiary"] if done else t["onSurfaceVariant"]
    win.result_counts.setText(tr("result.counts", ok=len(done), fail=len(failed)))
    win.result_counts.setStyleSheet(
        f'font-family:"Menlo","Consolas",monospace;font-size:12px;color:{ok_color};')

    while win.result_fails.count():
        w = win.result_fails.takeAt(0).widget()
        if w:
            w.deleteLater()
    for it in failed[:5]:
        lbl = QLabel(f"⚠ {it.name} → {(it.target_fmt or '').upper()}\n{tr(it.error_key or 'err.engine')}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"background:{t['errorContainer']};color:{t['onErrorContainer']};"
            "border-radius:8px;padding:8px;font-size:11px;")
        win.result_fails.addWidget(lbl)

    renamed = [it for it in done if it.renamed]
    notes = []
    if done:
        notes.append(tr("result.saved_n", n=len(done)))
    if renamed:
        notes.append(tr("result.renamed", name=renamed[0].output.name))
    win.result_note.setText("\n".join(notes))
    win.result_note.setVisible(bool(notes))
    win.open_folder_btn.setVisible(bool(done))

    # 저장 위치 안내(외부 QA 피드백) — 최근 기록 창을 따로 열어야만
    # 저장 경로를 알 수 있던 문제. 결과가 폴더 자체(PDF→이미지, DEC-025)면
    # 그 폴더를, 파일이면 부모 폴더를 "위치"로 본다(open_folder_btn과
    # 같은 원칙) — 중복 없이 등장 순서대로, 너무 길어지지 않게 최대
    # 3곳까지만 보여주고 나머지는 개수로 요약한다.
    while win.result_locations.count():
        w = win.result_locations.takeAt(0).widget()
        if w:
            w.deleteLater()
    # 대소문자만 다른 경로는 같은 폴더로 본다 — Windows(NTFS)·macOS
    # 기본(APFS)은 대소문자를 구분하지 않는 파일시스템이라, 단순 문자열
    # 비교로 중복을 제거하면 같은 폴더가 서로 다른 항목으로 두 번 표시될
    # 수 있다(외부 QA 피드백 리뷰로 발견).
    locations = []
    seen_lower = set()
    for it in done:
        loc = str(it.output if it.output.is_dir() else it.output.parent)
        key = loc.casefold()
        if key not in seen_lower:
            seen_lower.add(key)
            locations.append(loc)
    for loc in locations[:3]:
        lbl = QLabel(f"📂 {loc}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f'font-family:"Menlo","Consolas",monospace;font-size:10px;color:{t["onSurfaceVariant"]};')
        win.result_locations.addWidget(lbl)
    if len(locations) > 3:
        more = QLabel(tr("result.location_more", n=len(locations) - 3))
        more.setObjectName("muted")
        win.result_locations.addWidget(more)
    win.overlay.setGeometry(win.centralWidget().rect())
    win.overlay.show()
    win.overlay.raise_()
    win.result_ok_btn.setFocus()


def open_result_folder(win):
    done = next((it for it in win.items if it.state == ItemState.DONE and it.output), None)
    if done:
        # PDF→이미지(DEC-025)처럼 결과물 자체가 폴더면 그 폴더를 직접 연다 —
        # 그 외(파일 결과물)는 지금까지처럼 부모 폴더를 연다.
        target = done.output if done.output.is_dir() else done.output.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def dismiss_result(win):
    """확인: 전체 성공 → 목록 비움 / 실패 존재 → 실패 파일만 남김 (재시도, INV-03)."""
    win.overlay.hide()
    failed_ids = {it.id for it in win.items if it.state == ItemState.FAILED}
    for it in list(win.items):
        if it.id not in failed_ids:
            win._remove_item(it.id)
    for it in win.items:
        it.state = ItemState.QUEUED
        row = win.rows[it.id]
        row.set_locked(False)
        row.badge.hide()
        row.reason.hide()
    win._refresh_state()
