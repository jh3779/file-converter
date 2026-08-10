"""메인 창 — 정본: docs/03_screen_contract.md SCR-001~003 · 와이어프레임 S-01~S-06.

원스크린 드롭존(DEC-006) · 결과는 오버레이(DEC-008) · 언어 ko/en(DEC-009).
"""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QProgressBar, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from .. import converters, i18n, update_check
from ..history import History
from ..i18n import tr
from ..models import FileItem, ItemState
from ..update_check import UpdateChecker
from ..workers import Job

_ICONS = {"docx": "📄", "pdf": "📄", "hwp": "📄", "hwpx": "📄", "txt": "📄", "pptx": "📽",
          "csv": "📊", "xlsx": "📊", "json": "📊",
          "avi": "🎬", "mov": "🎬", "mkv": "🎬", "wmv": "🎬", "flv": "🎬",
          "webm": "🎬", "m4v": "🎬",
          "jpg": "🖼", "jpeg": "🖼", "png": "🖼", "bmp": "🖼", "gif": "🖼",
          "webp": "🖼", "tiff": "🖼"}

_BADGE = {  # state → (bg 토큰, fg 토큰, i18n 키)
    ItemState.QUEUED: ("stQueuedBg", "stQueuedFg", "st.queued"),
    ItemState.CONVERTING: ("stConvBg", "stConvFg", "st.converting"),
    ItemState.DONE: ("stDoneBg", "stDoneFg", "st.done"),
    ItemState.FAILED: ("stFailBg", "stFailFg", "st.failed"),
    ItemState.SKIPPED: ("stSkipBg", "stSkipFg", "st.skipped"),
}


class FileRow(QFrame):
    """C-02 FileRow. 변환 중엔 셀렉트·제거 대신 상태 배지 (입력 잠금)."""

    def __init__(self, item: FileItem, tokens: dict, on_remove, on_format_changed):
        super().__init__()
        self.setObjectName("fileRow")
        self.item = item
        self.tokens = tokens
        self._on_format_changed = on_format_changed

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        self.icon = QLabel(_ICONS.get(item.source_fmt, "🚫") if item.target_fmt is not None or converters.supported(item.source_fmt) else "🚫")
        lay.addWidget(self.icon)

        mid = QVBoxLayout()
        mid.setSpacing(0)
        self.name = QLabel(item.name)
        self.name.setStyleSheet("font-weight:600;")
        self.reason = QLabel("")
        self.reason.setObjectName("reason")
        self.reason.hide()
        mid.addWidget(self.name)
        mid.addWidget(self.reason)
        lay.addLayout(mid, 1)

        self.fmt_label = QLabel(item.source_fmt.upper() + " →")
        self.fmt_label.setObjectName("muted")
        lay.addWidget(self.fmt_label)

        self.combo = QComboBox()
        self.combo.setMinimumWidth(84)
        targets = converters.targets_for(item.source_fmt)
        self.combo.addItem(tr("pick.placeholder"), None)
        for t in targets:
            self.combo.addItem(t.upper(), t)
        self.combo.currentIndexChanged.connect(self._format_picked)
        lay.addWidget(self.combo)

        self.badge = QLabel("")
        self.badge.hide()
        lay.addWidget(self.badge)

        self.remove_btn = QPushButton("✕")
        self.remove_btn.setProperty("variant", "icon")
        self.remove_btn.setAccessibleName("remove file")
        self.remove_btn.clicked.connect(lambda: on_remove(self.item.id))
        lay.addWidget(self.remove_btn)

        if not converters.supported(item.source_fmt):
            # 행 전체(self)를 setEnabled(False)하면 Qt에서는 부모가 비활성화된
            # 자식에게 클릭이 전달되지 않는다 — remove_btn.setEnabled(True)를
            # 뒤에 호출해도 무시된다(부모 비활성 상태가 우선). "✕" 버튼만은
            # 계속 눌리게 해야 해서(파일 제거는 항상 가능해야 함) 회색으로
            # 보여줄 요소들만 개별적으로 비활성화한다 — 실사용 테스트에서
            # 재현된 버그: 지원 안 되는 파일을 X로 못 지움.
            self.icon.setEnabled(False)
            self.name.setEnabled(False)
            self.fmt_label.setEnabled(False)
            self.combo.hide()
            self.fmt_label.setText(tr("unsupported"))

    def _format_picked(self, _):
        self.item.target_fmt = self.combo.currentData()
        self._update_note()
        self._on_format_changed()

    def _update_note(self):
        """레이아웃/구조 단순화 고지 (muted, 오류 아님).
        DEC-037부터 PDF → DOCX는 줄 단위 절대 위치로 재구성돼(DEC-010의
        "흐르는 문서로 단순화"에서 전환) 전용 고지(note.pdf_to_docx, 편집
        시 줄이 자연스럽게 안 이어질 수 있다는 트레이드오프 안내)를 쓴다.
        HWP → DOCX는 아직 이 전환 전이라 기존 단순화 고지 그대로. DEC-028부터
        DOCX → HWP도 표는 실제 HWP 표로 만들어지지만(DEC-017 정정) 셀 병합·
        정밀한 레이아웃까지는 아니라 같은 고지를 쓴다. DEC-023: PDF → HWP도
        텍스트 기반이라 같은 고지(PDF 자체가 표 구조를 안 담고 있어 표 전용
        문구는 아님). QA(h) Phase 1: HWPX → DOCX/PDF도 같은 고지(셀 병합·
        머리말/꼬리말·문단 정렬이 아직 범위 밖 — spike/hwpxlib/RESULT.md).
        XLSX → CSV 선택 시 시트가 여러 개면 고지(첫 시트만 변환 — 여러
        파일로 나눠 출력하는 방안은 데이터 모델을 바꿔야 해서 별도 과제로
        보류). 애니메이션 이미지(GIF/WEBP) → 다른 이미지 포맷 선택 시 첫
        프레임만 남는다는 고지(항상 단일 프레임으로 단순화). DEC-026: PDF →
        이미지(PNG/JPG, DEC-043) 선택 시 결과가 폴더로 저장된다는 고지.
        DEC-030: PDF → PPTX 선택 시 표 테두리·이미지는 옮겨지지 않는다는
        고지(텍스트는 위치까지 재구성됨)."""
        if self.item.target_fmt == "docx" and self.item.source_fmt == "pdf":
            note_key = "note.pdf_to_docx"
        elif self.item.target_fmt == "docx" and self.item.source_fmt == "hwp":
            note_key = "note.simplified"
        elif self.item.target_fmt in ("docx", "pdf") and self.item.source_fmt == "hwpx":
            # QA(h) Phase 1: hwpx_to_pdf도 내부적으로 hwpx_to_docx를 거치므로
            # (hwp_to_pdf가 hwp_to_docx를 거치는 것과 같은 구조) 두 타겟 모두
            # 같은 단순화 고지를 쓴다.
            note_key = "note.simplified"
        elif self.item.target_fmt == "hwp" and self.item.source_fmt in ("docx", "pdf"):
            note_key = "note.simplified"
        elif self.item.target_fmt in ("png", "jpg") and self.item.source_fmt == "pdf":
            note_key = "note.pdf_to_images"
        elif self.item.target_fmt == "pptx" and self.item.source_fmt == "pdf":
            note_key = "note.pdf_to_pptx"
        elif self.item.target_fmt == "csv" and self.item.source_fmt == "xlsx":
            from ..converters.data import xlsx_sheet_count
            note_key = "note.xlsx_multisheet" if xlsx_sheet_count(self.item.source) > 1 else None
        elif (self.item.source_fmt in ("gif", "webp", "tiff")
              and self.item.target_fmt in ("jpg", "png", "bmp", "gif", "webp", "tiff")):
            from ..converters.image import is_animated
            note_key = "note.image_first_frame" if is_animated(self.item.source) else None
        else:
            note_key = None
        if note_key:
            self.reason.setStyleSheet(
                f"color:{self.tokens['onSurfaceVariant']};font-size:11px;")
            self.reason.setText(tr(note_key))
            self.reason.show()
        else:
            self.reason.hide()

    def set_locked(self, locked: bool):
        self.combo.setVisible(not locked and converters.supported(self.item.source_fmt))
        self.remove_btn.setVisible(not locked)
        self.fmt_label.setVisible(True)
        if locked and self.item.target_fmt:
            self.fmt_label.setText(f"{self.item.source_fmt.upper()} → {self.item.target_fmt.upper()}")

    def refresh(self):
        """상태 → 배지·사유 반영 (P-02: 색+아이콘+텍스트)."""
        it, t = self.item, self.tokens
        if it.state == ItemState.QUEUED and not self.badge.isVisible() and self.combo.isVisible():
            pass  # 목록 편집 중엔 배지 없음
        bg, fg, key = _BADGE[it.state]
        icon = {"st.queued": "🕘", "st.converting": "⟳", "st.done": "✓",
                "st.failed": "⚠", "st.skipped": "→"}[key]
        self.badge.setText(f"{icon} {tr(key)}")
        self.badge.setStyleSheet(
            f"background:{t[bg]};color:{t[fg]};border-radius:10px;"
            "padding:2px 10px;font-size:11px;font-weight:600;")
        self.setProperty("failed", "true" if it.state == ItemState.FAILED else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if it.state == ItemState.FAILED and it.error_key:
            self.reason.setStyleSheet(f"color:{t['error']};font-size:11px;")
            self.reason.setText(tr(it.error_key))
            self.reason.show()
        else:
            self.reason.hide()

    def retranslate(self):
        if not converters.supported(self.item.source_fmt):
            self.fmt_label.setText(tr("unsupported"))
        elif self.combo.count():
            self.combo.setItemText(0, tr("pick.placeholder"))
        if self.badge.isVisible():
            self.refresh()
        elif self.item.state == ItemState.QUEUED:
            self._update_note()


class MainWindow(QMainWindow):
    def __init__(self, tokens: dict):
        super().__init__()
        self.tokens = tokens
        self.items: list[FileItem] = []
        self.rows: dict[int, FileRow] = {}
        self._next_id = 1
        self.job: Job | None = None
        self.history = History()
        self._latest_version = ""
        self.update_checker = UpdateChecker()
        self.update_checker.found.connect(self._on_update_found)

        self.setAcceptDrops(True)
        self.setMinimumSize(640, 480)
        self.resize(720, 520)
        self._build()
        self.retranslate()
        self._refresh_state()
        self.drop_big.setFocus()
        if update_check.is_enabled():
            self.update_checker.check()

    # ---------- UI 구성 ----------
    def _build(self):
        t = self.tokens
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 헤더 (타이틀바 아래 앱 헤더)
        header = QHBoxLayout()
        header.setContentsMargins(16, 10, 12, 10)
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight:700;font-size:14px;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.history_btn = QPushButton("🕘")
        self.history_btn.setProperty("variant", "icon")
        self.history_btn.setAccessibleName("history")
        self.history_btn.clicked.connect(self._toggle_history)
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setProperty("variant", "icon")
        self.settings_btn.setAccessibleName("settings")
        self.settings_btn.clicked.connect(self._settings_menu)
        header.addWidget(self.history_btn)
        header.addWidget(self.settings_btn)
        root.addLayout(header)

        # 본문: 좌(메인) + 우(기록 패널)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)

        main_col = QVBoxLayout()
        main_col.setContentsMargins(16, 0, 16, 0)
        main_col.setSpacing(8)
        body.addLayout(main_col, 1)

        # 드롭존 (empty: 대형 / list: strip — C-01)
        self.drop_big = QPushButton()
        self.drop_big.setMinimumHeight(220)
        self.drop_big.setCursor(Qt.PointingHandCursor)
        self.drop_big.setStyleSheet(
            f"border:2px dashed {t['outline']};border-radius:12px;"
            f"background:{t['surfaceContainerLowest']};color:{t['onSurfaceVariant']};font-size:14px;")
        self.drop_big.clicked.connect(self._browse)
        main_col.addWidget(self.drop_big, 1)

        self.drop_strip = QPushButton()
        self.drop_strip.setCursor(Qt.PointingHandCursor)
        self.drop_strip.setStyleSheet(
            f"border:2px dashed {t['outline']};border-radius:10px;padding:7px;"
            f"background:{t['surfaceContainerLowest']};color:{t['onSurfaceVariant']};font-size:12px;")
        self.drop_strip.clicked.connect(self._browse)
        main_col.addWidget(self.drop_strip)

        # 파일 목록
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setSpacing(3)
        main_col.addWidget(self.list, 3)

        # 기록 패널 (S-05)
        self.history_panel = QFrame()
        self.history_panel.setObjectName("historyPanel")
        self.history_panel.setFixedWidth(260)
        hp = QVBoxLayout(self.history_panel)
        hp.setContentsMargins(12, 10, 12, 10)
        hp.setSpacing(6)
        hp_head = QHBoxLayout()
        self.hist_title = QLabel()
        self.hist_title.setStyleSheet("font-weight:700;font-size:13px;")
        hp_head.addWidget(self.hist_title, 1)
        self.hist_clear = QPushButton()
        self.hist_clear.setProperty("variant", "error")
        self.hist_clear.clicked.connect(self._confirm_clear_history)
        hp_head.addWidget(self.hist_clear)
        hp.addLayout(hp_head)
        self.hist_local = QLabel()
        self.hist_local.setObjectName("shield")
        self.hist_local.setWordWrap(True)
        hp.addWidget(self.hist_local)
        self.hist_list = QVBoxLayout()
        self.hist_list.setSpacing(4)
        hist_scroll_inner = QWidget()
        hist_scroll_inner.setLayout(self.hist_list)
        self.hist_scroll = QScrollArea()
        self.hist_scroll.setWidgetResizable(True)
        self.hist_scroll.setFrameShape(QFrame.NoFrame)
        self.hist_scroll.setWidget(hist_scroll_inner)
        hp.addWidget(self.hist_scroll, 1)
        self.history_panel.hide()
        body.addWidget(self.history_panel)

        # 푸터 (P-05 상시 고지 + 변환하기 / converting: 진행+취소)
        footer = QFrame()
        footer.setObjectName("footer")
        f = QVBoxLayout(footer)
        f.setContentsMargins(16, 8, 16, 12)
        f.setSpacing(6)

        self.progress_row = QHBoxLayout()
        self.progress_label = QLabel()
        self.progress_label.setStyleSheet("font-weight:600;font-size:12px;")
        self.progress_count = QLabel()
        self.progress_count.setStyleSheet('font-family:"Menlo","Consolas",monospace;font-size:11px;')
        self.progress_row.addWidget(self.progress_label)
        self.progress_row.addStretch(1)
        self.progress_row.addWidget(self.progress_count)
        f.addLayout(self.progress_row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        f.addWidget(self.progress)

        bottom = QHBoxLayout()
        self.shield = QLabel()
        self.shield.setObjectName("shield")
        bottom.addWidget(self.shield)
        self.update_notice = QLabel()
        self.update_notice.setObjectName("hint")
        self.update_notice.setCursor(Qt.PointingHandCursor)
        self.update_notice.hide()
        self.update_notice.mousePressEvent = lambda e: self._open_release_page()
        bottom.addWidget(self.update_notice)
        bottom.addStretch(1)
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        bottom.addWidget(self.hint)
        self.cancel_btn = QPushButton()
        self.cancel_btn.setProperty("variant", "outlined")
        self.cancel_btn.clicked.connect(self._cancel_job)
        bottom.addWidget(self.cancel_btn)
        self.convert_btn = QPushButton()
        self.convert_btn.setProperty("variant", "filled")
        self.convert_btn.clicked.connect(self._start_job)
        bottom.addWidget(self.convert_btn)
        f.addLayout(bottom)
        root.addWidget(footer)

        # 결과 오버레이 (DEC-008 · S-04)
        self.overlay = QFrame(central)
        self.overlay.setObjectName("overlay")
        self.overlay.setStyleSheet("QFrame#overlay{background:rgba(0,0,0,0.35);}")
        ov = QVBoxLayout(self.overlay)
        ov.setAlignment(Qt.AlignCenter)
        self.result_card = QFrame()
        self.result_card.setObjectName("resultCard")
        self.result_card.setStyleSheet(
            f"QFrame#resultCard{{background:{t['surfaceContainerLow']};border-radius:16px;}}"
            "QFrame#resultCard QLabel{background:transparent;}")
        self.result_card.setFixedWidth(360)
        rc = QVBoxLayout(self.result_card)
        rc.setContentsMargins(18, 16, 18, 14)
        rc.setSpacing(8)
        self.result_title = QLabel()
        self.result_title.setStyleSheet("font-weight:700;font-size:14px;")
        self.result_counts = QLabel()
        self.result_counts.setStyleSheet('font-family:"Menlo","Consolas",monospace;font-size:12px;')
        self.result_fails = QVBoxLayout()
        self.result_note = QLabel()
        self.result_note.setObjectName("muted")
        self.result_note.setWordWrap(True)
        self.result_locations = QVBoxLayout()  # 저장 위치 안내(외부 QA 피드백)
        self.result_locations.setSpacing(2)
        rc.addWidget(self.result_title)
        rc.addWidget(self.result_counts)
        rc.addLayout(self.result_fails)
        rc.addWidget(self.result_note)
        rc.addLayout(self.result_locations)
        btns = QHBoxLayout()
        btns.addStretch(1)
        self.open_folder_btn = QPushButton()
        self.open_folder_btn.setProperty("variant", "text")
        self.open_folder_btn.clicked.connect(self._open_result_folder)
        self.result_ok_btn = QPushButton()
        self.result_ok_btn.setProperty("variant", "filled")
        self.result_ok_btn.clicked.connect(self._dismiss_result)
        btns.addWidget(self.open_folder_btn)
        btns.addWidget(self.result_ok_btn)
        rc.addLayout(btns)
        ov.addWidget(self.result_card)
        self.overlay.hide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.overlay.setGeometry(self.centralWidget().rect())

    # ---------- i18n (DEC-009) ----------
    def retranslate(self):
        self.setWindowTitle(tr("app.title"))
        self.title_label.setText("⇄ " + tr("app.title"))
        self.drop_big.setText(f"📥\n\n{tr('drop.title')}\n{tr('drop.sub')}")
        self.drop_strip.setText(tr("drop.strip"))
        self.shield.setText("🔒 " + (tr("footer.save") if self.items else tr("footer.offline")))
        self.convert_btn.setText(tr("convert"))
        self.cancel_btn.setText(tr("cancel"))
        self.progress_label.setText(tr("converting"))
        self.hist_title.setText(tr("history.title"))
        self.hist_clear.setText(tr("history.clear"))
        self.hist_local.setText("🔒 " + tr("history.local"))
        self.result_ok_btn.setText(tr("ok"))
        self.open_folder_btn.setText(tr("result.openfolder"))
        if self._latest_version:
            self.update_notice.setText(tr("update.available", version=self._latest_version))
        for row in self.rows.values():
            row.retranslate()
        if self.history_panel.isVisible():
            self._reload_history()
        self._refresh_state()

    def _settings_menu(self):
        menu = QMenu(self)
        lang_menu = menu.addMenu(tr("lang.menu"))
        group = QActionGroup(lang_menu)
        pref = i18n.saved_pref()
        for value, key in (("", "lang.system"), ("ko", "lang.ko"), ("en", "lang.en")):
            act = QAction(tr(key), lang_menu, checkable=True)
            act.setChecked(pref == value)
            act.triggered.connect(lambda _, v=value: self._set_language(v))
            group.addAction(act)
            lang_menu.addAction(act)
        update_act = QAction(tr("settings.update_check"), menu, checkable=True)
        update_act.setChecked(update_check.is_enabled())
        update_act.triggered.connect(self._toggle_update_check)
        menu.addAction(update_act)
        menu.exec(self.settings_btn.mapToGlobal(self.settings_btn.rect().bottomLeft()))

    def _toggle_update_check(self, checked: bool):
        """OQ-002 해소(DEC-022): 옵트인, 기본 꺼짐. 버전 번호만 조회하고
        파일은 전송하지 않는다 — 켜는 순간 즉시 한 번 확인해 피드백을 준다."""
        update_check.set_enabled(checked)
        if checked:
            self.update_checker.check()
        else:
            self._latest_version = ""
            self.update_notice.hide()

    def _on_update_found(self, version: str):
        self._latest_version = version
        if version:
            self.update_notice.setText(tr("update.available", version=version))
            self.update_notice.show()
        else:
            self.update_notice.hide()

    def _open_release_page(self):
        QDesktopServices.openUrl(QUrl(f"https://github.com/{update_check.REPO}/releases"))

    def _set_language(self, value: str):
        i18n.set_lang(value or None)
        self.retranslate()

    # ---------- 파일 추가 (REQ-F-001) ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and self.job is None:
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_files([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])

    def _browse(self):
        if self.job is not None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, tr("drop.title"))
        self.add_files([Path(p) for p in paths])

    def add_files(self, paths: list[Path]):
        for p in paths:
            if not p.is_file():
                continue
            item = FileItem(self._next_id, p, p.suffix.lstrip(".").lower())
            self._next_id += 1
            self.items.append(item)
            row = FileRow(item, self.tokens, self._remove_item, self._refresh_state)
            self.rows[item.id] = row
            lw_item = QListWidgetItem()
            lw_item.setSizeHint(row.sizeHint())
            lw_item.setData(Qt.UserRole, item.id)
            self.list.addItem(lw_item)
            self.list.setItemWidget(lw_item, row)
        self._refresh_state()

    def _remove_item(self, item_id: int):
        self.items = [it for it in self.items if it.id != item_id]
        self.rows.pop(item_id, None)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == item_id:
                self.list.takeItem(i)
                break
        self._refresh_state()

    # ---------- 상태 갱신 (SCR-001 empty/list/converting) ----------
    def _refresh_state(self):
        converting = self.job is not None
        has_items = bool(self.items)
        self.drop_big.setVisible(not has_items and not converting)
        self.drop_strip.setVisible(has_items and not converting)
        self.list.setVisible(has_items)
        self.progress.setVisible(converting)
        self.progress_label.setVisible(converting)
        self.progress_count.setVisible(converting)
        self.cancel_btn.setVisible(converting)
        self.convert_btn.setVisible(not converting)
        self.history_btn.setEnabled(not converting)
        self.shield.setText("🔒 " + (tr("footer.save") if has_items else tr("footer.offline")))

        convertible = [it for it in self.items if converters.supported(it.source_fmt)]
        missing = [it for it in convertible if it.target_fmt is None]
        ready = bool(convertible) and not missing
        self.convert_btn.setEnabled(ready and not converting)
        self.hint.setText(tr("hint.pickformat") if (convertible and missing and not converting) else "")

    # ---------- 변환 (FLOW-001) ----------
    def _start_job(self):
        targets = [it for it in self.items
                   if converters.supported(it.source_fmt) and it.target_fmt]
        if not targets:
            return
        for it in targets:
            it.state = ItemState.QUEUED
            it.error_key = None
        target_ids = {it.id for it in targets}
        for item_id, row in self.rows.items():
            row.set_locked(True)          # 미참여 행 포함 전체 입력 잠금 (SCR-001 converting)
            if item_id in target_ids:
                row.badge.show()
                row.refresh()
        self.drop_strip.hide()
        self._done_count = 0
        self._total = len(targets)
        self.progress.setMaximum(self._total)
        self.progress.setValue(0)
        self.progress_count.setText(tr("progress.n", done=0, total=self._total))

        self.job = Job(targets)
        s = self.job.signals
        s.item_started.connect(self._on_started)
        s.item_done.connect(self._on_done)
        s.item_failed.connect(self._on_failed)
        s.item_skipped.connect(self._on_skipped)
        s.job_finished.connect(self._on_job_finished)
        self._refresh_state()
        self.job.start()

    def _find(self, item_id: int) -> FileItem:
        return next(it for it in self.items if it.id == item_id)

    def _bump(self):
        self._done_count += 1
        self.progress.setValue(self._done_count)
        self.progress_count.setText(tr("progress.n", done=self._done_count, total=self._total))

    def _on_started(self, item_id: int):
        it = self._find(item_id)
        it.state = ItemState.CONVERTING
        self.rows[item_id].refresh()

    def _on_done(self, item_id: int, output: str, renamed: bool):
        it = self._find(item_id)
        it.state = ItemState.DONE
        it.output = Path(output)
        it.renamed = renamed
        self.rows[item_id].refresh()
        self._record_history(it.name, it.target_fmt, output, True)
        self._bump()

    def _on_failed(self, item_id: int, key: str):
        it = self._find(item_id)
        it.state = ItemState.FAILED
        it.error_key = key
        self.rows[item_id].refresh()
        self._record_history(it.name, it.target_fmt or "", "", False)
        self._bump()

    def _record_history(self, name: str, target_fmt: str, output_path: str, success: bool):
        """기록을 저장하고, 기록 패널이 이미 열려 있으면 그 자리에서 바로
        새로고침한다 — 이전엔 패널을 껐다 켜야만(_toggle_history) 새 항목이
        보였다(외부 QA 피드백)."""
        self.history.add(name, target_fmt, output_path, success)
        if self.history_panel.isVisible():
            self._reload_history()

    def _on_skipped(self, item_id: int):
        it = self._find(item_id)
        it.state = ItemState.SKIPPED
        self.rows[item_id].refresh()
        self._bump()

    def _cancel_job(self):
        if self.job:
            self.job.cancel()

    def _on_job_finished(self):
        self.job = None
        self._show_result()
        self._refresh_state()

    # ---------- 결과 오버레이 (SCR-002 · DEC-008) ----------
    def _show_result(self):
        done = [it for it in self.items if it.state == ItemState.DONE]
        failed = [it for it in self.items if it.state == ItemState.FAILED]
        t = self.tokens
        if not failed:
            self.result_title.setText("✅ " + tr("result.allsuccess"))
        elif done:
            self.result_title.setText("⚠️ " + tr("result.partial"))
        else:
            self.result_title.setText("❌ " + tr("result.allfail"))
        ok_color = t["tertiary"] if done else t["onSurfaceVariant"]
        self.result_counts.setText(tr("result.counts", ok=len(done), fail=len(failed)))
        self.result_counts.setStyleSheet(
            f'font-family:"Menlo","Consolas",monospace;font-size:12px;color:{ok_color};')

        while self.result_fails.count():
            w = self.result_fails.takeAt(0).widget()
            if w:
                w.deleteLater()
        for it in failed[:5]:
            lbl = QLabel(f"⚠ {it.name} → {(it.target_fmt or '').upper()}\n{tr(it.error_key or 'err.engine')}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"background:{t['errorContainer']};color:{t['onErrorContainer']};"
                "border-radius:8px;padding:8px;font-size:11px;")
            self.result_fails.addWidget(lbl)

        renamed = [it for it in done if it.renamed]
        notes = []
        if done:
            notes.append(tr("result.saved_n", n=len(done)))
        if renamed:
            notes.append(tr("result.renamed", name=renamed[0].output.name))
        self.result_note.setText("\n".join(notes))
        self.result_note.setVisible(bool(notes))
        self.open_folder_btn.setVisible(bool(done))

        # 저장 위치 안내(외부 QA 피드백) — 최근 기록 창을 따로 열어야만
        # 저장 경로를 알 수 있던 문제. 결과가 폴더 자체(PDF→이미지, DEC-025)면
        # 그 폴더를, 파일이면 부모 폴더를 "위치"로 본다(open_folder_btn과
        # 같은 원칙) — 중복 없이 등장 순서대로, 너무 길어지지 않게 최대
        # 3곳까지만 보여주고 나머지는 개수로 요약한다.
        while self.result_locations.count():
            w = self.result_locations.takeAt(0).widget()
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
            self.result_locations.addWidget(lbl)
        if len(locations) > 3:
            more = QLabel(tr("result.location_more", n=len(locations) - 3))
            more.setObjectName("muted")
            self.result_locations.addWidget(more)
        self.overlay.setGeometry(self.centralWidget().rect())
        self.overlay.show()
        self.overlay.raise_()
        self.result_ok_btn.setFocus()

    def _open_result_folder(self):
        done = next((it for it in self.items if it.state == ItemState.DONE and it.output), None)
        if done:
            # PDF→이미지(DEC-025)처럼 결과물 자체가 폴더면 그 폴더를 직접 연다 —
            # 그 외(파일 결과물)는 지금까지처럼 부모 폴더를 연다.
            target = done.output if done.output.is_dir() else done.output.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _dismiss_result(self):
        """확인: 전체 성공 → 목록 비움 / 실패 존재 → 실패 파일만 남김 (재시도, INV-03)."""
        self.overlay.hide()
        failed_ids = {it.id for it in self.items if it.state == ItemState.FAILED}
        for it in list(self.items):
            if it.id not in failed_ids:
                self._remove_item(it.id)
        for it in self.items:
            it.state = ItemState.QUEUED
            row = self.rows[it.id]
            row.set_locked(False)
            row.badge.hide()
            row.reason.hide()
        self._refresh_state()

    # ---------- 기록 패널 (SCR-003) ----------
    def _toggle_history(self):
        vis = not self.history_panel.isVisible()
        self.history_panel.setVisible(vis)
        if vis:
            self._reload_history()

    def _reload_history(self):
        while self.hist_list.count():
            w = self.hist_list.takeAt(0).widget()
            if w:
                w.deleteLater()
        entries = self.history.list()
        t = self.tokens
        if not entries:
            empty = QLabel(tr("history.empty"))
            empty.setObjectName("muted")
            self.hist_list.addWidget(empty)
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
            del_btn.clicked.connect(lambda _, i=e.id: (self.history.delete(i), self._reload_history()))
            rl.addWidget(del_btn)
            self.hist_list.addWidget(row)
        self.hist_list.addStretch(1)

    def _confirm_clear_history(self):
        if self._safe_dialog(tr("dlg.clear.title"), tr("dlg.clear.body"),
                             tr("cancel"), tr("dlg.clear.confirm")):
            self.history.clear()
            self._reload_history()

    # ---------- 다이얼로그 (C-08: 기본 포커스=안전 행동) ----------
    def _safe_dialog(self, title: str, body: str, safe: str, danger: str) -> bool:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        head = QLabel(title)
        head.setStyleSheet("font-weight:700;font-size:14px;")
        msg = QLabel(body)
        msg.setWordWrap(True)
        msg.setObjectName("muted")
        lay.addWidget(head)
        lay.addWidget(msg)
        btns = QHBoxLayout()
        btns.addStretch(1)
        safe_btn = QPushButton(safe)
        safe_btn.setProperty("variant", "filled")
        safe_btn.setDefault(True)
        danger_btn = QPushButton(danger)
        danger_btn.setProperty("variant", "error")
        safe_btn.clicked.connect(dlg.reject)
        danger_btn.clicked.connect(dlg.accept)
        btns.addWidget(safe_btn)
        btns.addWidget(danger_btn)
        lay.addLayout(btns)
        safe_btn.setFocus()
        return dlg.exec() == QDialog.Accepted

    def closeEvent(self, e):
        if self.job is not None:
            if self._safe_dialog(tr("dlg.quit.title"), tr("dlg.quit.body"),
                                 tr("dlg.quit.stay"), tr("dlg.quit.quit")):
                self.job.cancel()
                e.accept()
            else:
                e.ignore()
        else:
            e.accept()
