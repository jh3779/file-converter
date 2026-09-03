"""job(변환 작업) 생명주기 — main_window.py에 응집돼 있던 job 시작·진행
콜백·완료 처리를 분리했다(구조 감사 후속 조치, result_panel.py·
history_panel.py와 대칭).

각 함수는 MainWindow 인스턴스(win, 첫 인자 self)를 받아 그 상태를
갱신한다 — 클래스 정의부(main_window.py)에서 `_start_job = start_job`
처럼 메서드로 바인딩해, 테스트가 `win._record_history(...)`·
`win._on_job_finished()`처럼 기존 방식으로 호출하는 걸 그대로
유지한다(result_panel.py의 `win.result_scroll` 직접 접근 유지와
같은 이유).
"""
from pathlib import Path

from .. import converters
from ..i18n import tr
from ..models import ItemState
from ..workers import Job


def start_job(self):
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


def find_item(self, item_id: int):
    return next(it for it in self.items if it.id == item_id)


def bump_progress(self):
    self._done_count += 1
    self.progress.setValue(self._done_count)
    self.progress_count.setText(tr("progress.n", done=self._done_count, total=self._total))


def on_started(self, item_id: int):
    it = self._find(item_id)
    it.state = ItemState.CONVERTING
    self.rows[item_id].refresh()


def on_done(self, item_id: int, output: str, renamed: bool):
    it = self._find(item_id)
    it.state = ItemState.DONE
    it.output = Path(output)
    it.renamed = renamed
    self.rows[item_id].refresh()
    self._record_history(it.name, it.target_fmt, output, True)
    self._bump()


def on_failed(self, item_id: int, key: str):
    it = self._find(item_id)
    it.state = ItemState.FAILED
    it.error_key = key
    self.rows[item_id].refresh()
    self._record_history(it.name, it.target_fmt or "", "", False)
    self._bump()


def record_history(self, name: str, target_fmt: str, output_path: str, success: bool):
    """기록을 저장하고, 기록 패널이 이미 열려 있으면 그 자리에서 바로
    새로고침한다 — 이전엔 패널을 껐다 켜야만(_toggle_history) 새 항목이
    보였다(외부 QA 피드백)."""
    self.history.add(name, target_fmt, output_path, success)
    if self.history_panel.isVisible():
        self._reload_history()


def on_skipped(self, item_id: int):
    it = self._find(item_id)
    it.state = ItemState.SKIPPED
    self.rows[item_id].refresh()
    self._bump()


def cancel_job(self):
    if self.job:
        self.job.cancel()


def on_job_finished(self):
    self.job = None
    if self._quit_pending:
        # closeEvent가 취소 후 즉시 종료하지 않고 여기까지 미뤄둔
        # 상태(main_window.py의 closeEvent 참고) — 이제 실행 중이던
        # 워커가 전부 끝났으니(취소된 항목의 item_failed/item_done도
        # 이미 처리됨) 안전하게 다시 닫는다. self.job이 None이라
        # closeEvent가 이번엔 바로 history.close() + accept로 간다.
        self.close()
        return
    self._show_result()
    self._refresh_state()
